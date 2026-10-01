# Signals as time series (model, 2026-10-01)

A signal is not a variable but a **time series**. Rules read a signal's current value,
or a reduction of it. Decided with the user; not implemented as a registry yet.

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
