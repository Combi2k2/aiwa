# Signals as time series (model, 2026-10-01)

A signal is not a variable but a **time series**. Rules read a signal's current value,
or a reduction of it.

## Implemented (2026-10-01)

- `signals/series.py`: `Piecewise` (sorted pieces start, end, value; equal neighbours merged;
  gaps = unknown; the value at t is the piece with start < t ≤ end) and `Lazy` (known by
  `at(t)`, sampled every 10 s when pieces are needed). Counts are rates per minute.
- `signals/ops.py`: our own operators, not Polars (exact on intervals, no dependency):
  `lift` (pointwise, also + − * / comparisons and / or / not), `delay`, and over a trailing
  window `tssum` (∫ dt in minutes), `tsmean`, `tsmax`, `tsmin`, `tscount` (pieces begun).
- `signals/primitive.py`: app, title, site, category, away, active (timeline);
  keys, clicks, moved, scrolled (aw-watcher-input, per minute, `Context.inputs`).
- `Signal.expr`: e.g. `Signal("keys_5m", "tsmean(keys, 5m)")`, evaluated by
  `signals/expr.py` (Python syntax via `ast`, a whitelist, durations 30s / 5m / 2h / 1d).
  Names: primitives, other signals (as series: re-evaluated at shifted moments), state values.
  Signals without `expr` compute `eval` in Python (the focus score).
- Not yet: state as a series (in_session is only known now), kinds per segment, history
  beyond the lookback (reductions per day / week still live in metrics/).

## Series types

- **interval series**: a value over [start, end), piecewise constant (the window in focus)
- **event series**: values at points in time (input counts every 5 s)
- **sampled series**: a regular grid (the per-minute ledger)

## 1. Primitive series (recorded)

| Series | Type | Source |
|---|---|---|
| app, window title | interval | ActivityWatch window watcher |
| tab URL, tab title | interval | browser extension |
| away / present | interval | AFK watcher |
| **key intensity** (key presses / min) | event | aw-watcher-input (`presses` / 2: down and up are both counted) |
| **mouse intensity** (clicks, movement, scrolling / min) | event | aw-watcher-input (`clicks`, `deltaX/Y`, `scrollX/Y`) |
| in session, its goal group, current task | interval | aiwa's state |
| time | — | the clock |

**User answers are not primitive signals.** They are the inputs of chained workflows:
an action node's answer flows along an edge to the next node. When an answer must be
remembered for later signals (labelled breaks → usual meal times; notes that became
tasks; verdicts), a workflow node **writes a record**, and the record store is a source
for reductions, like any other history.

## 2. Derived series (one value per moment)

- **lookups** (per interval): URL → domain → category, kind; tracked / masked; lock screen →
  away; watching fills away; tools take the category of the work before
- **window operators** (numeric, over t, at τ = 2 / 5 / 30 min): depth, fit, hit rate,
  continuity, intensity (`signals/focus/`); input rate (`timeline.py`, to be split into key and
  mouse intensity); rise = intensity(t) − intensity(t − lag) (`rules/focus.py`)
- **resampling**: intensity and category per minute → the ledger (the one stored series)

## 3. Reductions (series → fewer values)

- per day / week: deep minutes, streaks, shallow share, first session start, quota
- distributions over weeks: density peak (off time, routine times), empirical CDF
  (reminders), median (consistency), quantile (low-focus threshold, later), weighted lift
  (window × goal)

## Operators

map (lookup) · window(τ, f) · lag · resample · group by day / week + aggregate (sum, count,
ratio, run length, streak) · distribution (density, CDF, median, quantile, lift) · and on
top, the rule: soft threshold → chance → sample, levels voting by majority.
