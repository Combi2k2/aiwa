"""Evaluate a signal's `expr`: a small time-series expression.

    tsmean(keys + clicks, 5m)
    tssum(category == "deep", 1h)
    tsmean(focus_2m, 2m) - delay(tsmean(focus_2m, 2m), 2m)
    tscount(active, 30m) > 3 and not in_session

Python's syntax, parsed with `ast` and walked by hand (no `eval`): numbers, text in
quotes, durations (30s, 5m, 2h, 1d), + - * /, comparisons, and / or / not, and the
functions of signals/ops.py. A name is a primitive series (signals/primitive.py),
another signal (as a series over time), or a state value of the app (a number).

Every operation works on whole series; the result is read at the context's moment.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import replace
from datetime import timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from aiwa.signals import ops
from aiwa.signals.primitive import PRIMITIVES, primitive
from aiwa.signals.series import Lazy, Series

if TYPE_CHECKING:
    from aiwa.signals.base import Context, Signal, Value

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
DURATION = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)([smhd])\b")

BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
           ast.Eq: operator.eq, ast.NotEq: operator.ne}


class ExprError(ValueError):
    pass


@lru_cache(maxsize=256)
def parse(expr: str) -> ast.expr:
    """The expression's syntax tree; durations become `__duration__(seconds)` calls."""
    source = DURATION.sub(lambda m: f"__duration__({float(m[1]) * UNITS[m[2]]})", expr)
    try:
        return ast.parse(source, mode="eval").body
    except SyntaxError as e:
        raise ExprError(f"can't read {expr!r}: {e.msg}") from None


def evaluate(expr: str, ctx: Context) -> Value:
    result = _eval(parse(expr), ctx)
    value = result.at(ctx.now) if isinstance(result, Series) else result
    return value if value is None or isinstance(value, (bool, int, float)) else None


def series_of(signal: Signal, ctx: Context) -> Series:
    """A signal as a series: its value at any moment, from the same timeline."""
    return Lazy(lambda t: signal.eval(ctx if t == ctx.now else replace(ctx, now=t)))


def _name(name: str, ctx: Context) -> Any:
    if name in PRIMITIVES:
        return primitive(name, ctx)
    if name in ctx.signals:
        return series_of(ctx.signals[name], ctx)
    if name in ctx.state:
        return ctx.state[name]
    raise ExprError(f"unknown name {name!r}")


def _eval(node: ast.expr, ctx: Context) -> Any:
    match node:
        case ast.Constant(value=value) if isinstance(value, (int, float, str, bool)):
            return value
        case ast.Name(id=name):
            return _name(name, ctx)
        case ast.Call(func=ast.Name(id="__duration__"), args=[ast.Constant(value=seconds)]):
            return timedelta(seconds=seconds)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in ops.FUNCTIONS:
            return ops.FUNCTIONS[name](*(_eval(a, ctx) for a in args))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in BINARY:
            f = BINARY[type(op)]
            return ops.lift(lambda a, b: None if f is operator.truediv and b == 0 else f(a, b),
                            _eval(left, ctx), _eval(right, ctx))
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return ops.lift(operator.neg, _eval(operand, ctx))
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return ops.lift(operator.not_, _eval(operand, ctx))
        case ast.BoolOp(op=op, values=values):
            combine = all if isinstance(op, ast.And) else any
            return ops.lift(lambda *vs: combine(bool(v) for v in vs), *(_eval(v, ctx) for v in values))
        case ast.Compare(left=left, ops=comparisons, comparators=rights) if all(type(c) in COMPARE for c in comparisons):
            operands = [_eval(left, ctx), *(_eval(r, ctx) for r in rights)]
            fs = [COMPARE[type(c)] for c in comparisons]
            return ops.lift(lambda *vs: all(f(a, b) for f, a, b in zip(fs, vs, vs[1:])), *operands)
    raise ExprError(f"not allowed in an expression: {ast.unparse(node)}")
