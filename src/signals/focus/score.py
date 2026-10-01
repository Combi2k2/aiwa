"""The focus score as signals (the components live next to this file)."""

from __future__ import annotations

from datetime import timedelta

from aiwa.signals.base import Context, Signal, Value
from aiwa.signals.focus.moment import moment
from aiwa.signals.focus.params import FocusParams


class Intensity(Signal):
    """Focus intensity over the last `horizon`: depth × fit × hit rate × continuity."""

    def __init__(self, name: str, horizon: timedelta, params: FocusParams):
        self.name, self.horizon, self.params = name, horizon, params

    def eval(self, ctx: Context) -> Value:
        return moment(ctx.segments, ctx.now, self.horizon, self.params).intensity


class Rise(Signal):
    """How much the intensity over `horizon` rose in the last `lag` (now − then)."""

    def __init__(self, name: str, horizon: timedelta, lag: timedelta, params: FocusParams):
        self.name, self.horizon, self.lag, self.params = name, horizon, lag, params

    def eval(self, ctx: Context) -> Value:
        now = moment(ctx.segments, ctx.now, self.horizon, self.params).intensity
        then = moment(ctx.segments, ctx.now - self.lag, self.horizon, self.params).intensity
        return None if now is None or then is None else now - then
