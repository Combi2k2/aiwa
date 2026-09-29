# aiwa components

Every part of aiwa is a small module with one job, explicit inputs and
outputs, its parameters in the config, and its own tests. To improve one part,
change that module (and its parameters) without touching the others.

## Data flow

```
ActivityWatch ─► collector ─► timeline ─► categories.prepare ─┬─► focus.* ─► tray status
                    │                                          └─► analyzer + rules ─► policy ─► nudges
                    └─► current() ─► classifier ─► popup ─► store
```

## Components

| Module | Job | Input → output | Tuned by (config) | Tests |
|---|---|---|---|---|
| `core/collector.py` | Read ActivityWatch | HTTP → raw `Segment`s; `current()` → what's in focus now | `[activitywatch]` | via command runs |
| `core/timeline.py` | Build one ordered timeline | windows + away periods + tabs → `Segment`s; `merge()` joins identical neighbours | — | `test_timeline.py` |
| `core/categories.py` | Categorize + hide untracked names | `Segment`s → categorized, masked `Segment`s | `[[category]]`, `[[track]]` | `test_timeline.py` |
| `core/classifier.py` | Decide when to ask about an app/site | what's in focus now → `Question` (track / classify / confirm) | `[classification]`, `[openjev] min_confidence` | `test_classifier.py` |
| `core/openjev.py` | Suggest a category | app name or domain → (category, confidence) | `[openjev]` | `test_timeline.py` (mocked) |
| `core/store.py` | Persist answers | categories, tracking choices, nudges, goal groups + task backlog, state values, sessions, plans ↔ SQLite | — | `test_core.py`, others |
| `core/focus/window.py` | Slice one window | `Segment`s, end, τ → stretches + switches (no scoring) | — | `test_focus.py` |
| `core/focus/depth.py` | How deep | window → [0, 1] | `shallow_weight` | `test_focus.py` |
| `core/focus/stability.py` | Stayed in a small working set? | window → fit × hit rate | `capacity` | `test_focus.py` |
| `core/focus/continuity.py` | Stayed on each item long enough? | window → [0, 1] | `dwell_scale_seconds` | `test_focus.py` |
| `core/focus/moment.py` | Score one moment | `Segment`s, t, τ → `Moment` (all components + intensity) | `horizons_minutes` | `test_focus.py` |
| `core/focus/period.py` | Summarize a period | `Segment`s, start, end → `Period` | `deep_threshold` | `test_focus.py` |
| `core/sampling.py` | When to ask "how focused are you? (1–5)" | now, away → due or not (random times in working hours, min gap) | `[sampling]` | `test_calibration.py` |
| `core/calibration.py` | Score vs. your ratings | ratings + segments → rank correlation per component; one-at-a-time parameter sweep | — | `test_calibration.py` |
| `core/scoreboard/ledger.py` | One saved entry per minute: focus intensity + main activity | segments → `MinuteEntry` per finished minute | — | `test_scoreboard.py` |
| `core/scoreboard/day.py` | A day's summary: deep minutes, streaks, time per activity, goal progress | minute entries → `DayScore` | `deep_threshold`, `[scoreboard]` | `test_scoreboard.py` |
| `core/scoreboard/keeper.py` | Score only new minutes (fill in the day at start); today's score | now → saved minutes; `DayScore` | `[scoreboard] day_starts`, `daily_goal_minutes` | `test_scoreboard.py` |
| `core/session.py` | Focus session behaviour: pokes while focus is low (build-up), "done?" then pokes (free), wrap-up reminders (50 min+), alarm when away | time, low focus?, away since → one `Action` | `[session]` | `test_session.py` |
| `core/schedule.py` | Today's deep-work block (evening plan, else the default rhythm); when the warm-up / start reminders are due | day, plan → `Block`; now → `Reminder` | `[rhythm]` | `test_rhythm.py` |
| `core/history.py` | Deep minutes per session; the chain of kept days | minute entries, outcomes → numbers | `kept_deep_minutes` | `test_rhythm.py` |
| `core/rhythm.py` | Glue: today's block, today's sessions, chain length from stored data | store → blocks, sessions, chain | `[rhythm]` | `test_rhythm.py` |
| `core/backlog.py` | The task backlog's logic: atomic or not (vague / over 50 min), estimate mismatch, workable tasks (steps before their parent), urgency (work left ÷ time to deadline), group choice (urgency × priority), next task | tasks, groups, now → answers | `SESSION_MINUTES`, `MISMATCH_RATIO`, `PRIORITY_WEIGHT` | `test_backlog.py` |
| `core/quota.py` | Daily deep-work quota: +1 h today past 80%; base +1 h after 3 days in a row past 80%; 4–10 h | deep minutes → quota | `[scoreboard] quota_*` | `test_backlog.py` |
| `core/openjev.py` `assess_task`, `suggest_group` | Deep or shallow, size, specific or vague; which existing goal group a task belongs to | task text → `Assessment` / group name | — | `test_backlog.py` |
| `core/ai.py` | The AI helper (Google Gemini, 3.5 Flash → 3.5 Flash Lite when busy): suggested steps when breaking a task down, a name for a new goal group; never adds tasks itself; time limit, model fallback, pause after failures | prompts → suggestions | `[ai]` | `test_ai.py` |
| `tasks_controller.py` | Task window, new/edit form, break-down dialog, evening "anything new?", one group's tasks per session | — | — | manual |
| `rhythm_prompts.py` | The block reminder and the timing of the evening prompt | — | `planning_time` | manual |
| `core/bedtime.py` | Evening wind-down: phase (day / wind-down / hard stop), pokes every 5 min while active, one "10 more minutes" per night, alarm from the hard stop while active | now, active? → `Action` | `[bedtime]` | `test_bedtime.py` |
| `bedtime_prompts.py` | Shows the wind-down popups, rings/silences its own alarm, locks the screen; logs last activity at night and first in the morning | — | — | manual |
| `core/morning.py` | Morning start: greet on the first activity, routine timer (time + clamp(20%, 5, 20) min), alarm when not back, then suggest the first session | now, active? → `Action` | — | `test_morning.py` |
| `morning_prompts.py` | Shows today's work and the routine question, rings its own alarm, suggests the session; once per day | — | — | manual |
| `core/routines.py` | Absences (away or laptop asleep, ≥ 5 min) → sometimes "what was that?" (chance by duration), likely activities by duration and time of day; the taxonomy; overnight = sleep | active? over time → `Absence`s | — | `test_routines.py` |
| `core/consistency.py` | Consistency of start times: usual start = median of each day's first session (last 14 days, ≥ 3 needed); days on time = first session within ±30 min, among the last 5 | first starts per day → `Consistency` | `ConsistencyParams` | `test_consistency.py` |
| `core/offline.py` | Offline work in a session: away on a task marked offline = the work (no away alarm or auto-end), credited as deep minutes; away past estimate + 30 min → only the estimate counts, then normal away rules | current task, away since, now → `OfflineStep` | `OFFLINE_GRACE`, `OFFLINE_LIKELY` in `backlog.py` | `test_offline.py` |
| `routine_prompts.py` | Stores every absence, asks about some (likely options, "Other…" → categories → activities, "Skip") | — | — | manual |
| `core/analyzer.py`, `core/rules/` | Notice patterns outside sessions (currently none active: parked until scheduled deep-work blocks) | `Segment`s → `Finding`s | per rule | `test_core.py` |
| `core/policy.py` | Allow an interruption? | `Finding`, now, away → yes/no | `[nudges]` | `test_core.py` |
| `services/activitywatch.py` | Run ActivityWatch's server + watchers instead of its own tray app; restart crashed ones; stop them on quit; take over leftovers from a crashed run | module commands → running processes | `[activitywatch] manage`, `modules` | `test_activitywatch.py` |
| `ui/` | Tray (scoreboard + block/chain/session/task lines, `board.py`), task window / form / break-down dialog (`task_board.py`, `task_form.py`, `breakdown.py`), background calls (`background.py`), scope icon with progress ring (`icon.py`), popup, inbox, looping alarm sound (`sound.py`, Qt audio) | — | `[session] alarm_sound`, `alarm_volume` | `test_scoreboard.py` (text), manual |
| `platforms/` | Per OS: start at login, where ActivityWatch is installed, lock the screen | — | — | manual |
| `assets/sounds/` | Built-in sounds, with `CREDITS.md` (source and license) | — | — | — |
| `app.py` | Wire it all into the tray app: 2 s poll + 15 s analysis; menu actions | — | `[analysis]` | manual |
| `cli.py` | Entry point: `aiwa` starts the tray app | — | — | — |
| `commands/` | Developer tools, one module per subcommand; `data.py` loads segments for all | — | — | via runs |

## Focus intensity

For a window of length τ ending at time t (`core/focus/moment.py`):

```
intensity = depth × fit × hit rate × continuity           each in [0, 1]
```

| Component | Formula | Parameter (default) |
|---|---|---|
| depth | Σ weight(category) × time / Σ time, neutral time left out; deep 1, shallow w, distraction 0, unclassified 0 | `shallow_weight` (0.3) |
| fit | min(1, capacity / exp(entropy of time per item)) | `capacity` (5) |
| hit rate | (hits + 1) / (switches + 1); a hit is a switch back to an item used within τ, never into a distraction | τ = window size |
| continuity | 1 − exp(−mean dwell / d₀), mean dwell = active time / (switches + 1) | `dwell_scale_seconds` (20) |

Undefined when less than 25% of the window is active, or all of it is neutral.
Measured at τ = 2, 10, 30 min (`horizons_minutes`); the middle one is the main score.

A **period** (`core/focus/period.py`) samples the main score every minute and
reports mean intensity, deep minutes (score ≥ `deep_threshold`, 0.6), the
longest deep streak, switches into distraction per hour, and the share of time active.

**Calibrating:** aiwa asks for a 1–5 focus rating a few times a day (and on
demand from the tray). `core/calibration.py` reports how well each component
agrees with those ratings, and from 20 ratings on, which parameter values agree
best (`aiwa calibrate` for now; a tray entry once enough ratings exist).

Public-data check: `benchmarks/swell_kw.py`, results in `docs/benchmarks.md`
(interruptions lower the score for 20 of 23 people; fit and hit rate untested there).
