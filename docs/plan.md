# Plan: Deep Work philosophy in aiwa

> 2026-09-28: aiwa is used through the tray app; `aiwa` alone starts it. The CLI
> subcommands remain as developer tools. A GUI comes only after all features.

## Context
aiwa (`~/Documents/aiwa`) is a tray daemon: every 60 s it reads window events from
ActivityWatch, runs rules, and nudges through a rate-limiting policy. Today it has one rule
(fragmentation), ignores AFK, and has no notion of deep vs. shallow work, sessions, plans or
goals. `docs/deep-work.md` lists 35 Deep Work ideas to integrate. This plan turns them into
phased, shippable steps that use only what ActivityWatch and openjev can actually provide.

## What the data sources can and can't do
- **ActivityWatch**: focused app + window title (`currentwindow`), AFK periods (`afkstatus`),
  active browser tab URL/title (web extension), current file/project (VS Code plugin),
  optional input counts. It only sees what is in focus, never window content.
- **openjev**: structured decisions only. `noul` gives a probability, `choice` gives a label
  plus probabilities. It can't write free text. It's free today (crypto-funded), with no
  stated privacy policy or rate limits. So it's **optional**, sits behind an interface, and
  only receives **summaries**, never raw titles or URLs (except for classification, and only
  if the user opts in).
- Anything needing text generation (weekly summaries) uses templates for now.

## Architecture changes (all in `src/aiwa/core/` unless noted)
| New module | Purpose | Reuses |
|---|---|---|
| `timeline.py` | Merge window + AFK + web (+ editor) buckets into `Segment(start, end, app, title, url, category, away)` | `collector.py` (extend `Collector` to read AFK/web buckets; keep the allowlist → `(untracked)` masking) |
| `categories.py` | User rules (app/title/url regex → `deep` / `shallow` / `distraction` / `neutral`); unknown activities are rated once and cached | `config.py` `TrackRule` pattern |
| `sessions.py` | Focus sessions (duration, allowed categories, goal, mode: normal / sprint / grand-gesture) and day-plan blocks (deep / shallow / collab / distraction-window) | `store.py` |
| `metrics.py` | Focus intensity of a moment, measured over sliding windows of several sizes (working set, hit rate, deep share; see "Focus metric" below); deep hours built from it; hours per goal | — |
| `decider.py` | `Decider` protocol: `decide(summary) -> (interrupt_p, nudge)`. Implementations: `RulesDecider` (default) and `OpenjevDecider` (optional) | `policy.py` calls it after a rule fires |
| `rules/*.py` | One file per pattern (see phases) | `analyzer.py` `Rule` protocol, `rules/fragmentation.py` as the template |
| `ui/*.py` | Scoreboard in tray; popups: plan day, start session, rate activity, shutdown, weekly review | `ui/popup.py`, `ui/tray.py`, `ui/inbox.py` |

Rules change from `check(events, now)` to `check(ctx, now)`, where `ctx` bundles the timeline,
the active session/plan block and metrics. The policy gains: never nudge while away, no
nudges during a deep session except severe ones, and prefer break points (return from AFK,
session end).

Store: new tables `categories`, `sessions`, `plan_blocks`, `goals`, `daily_scores`, `experiments`.

## Phases (each ends usable; checklist items in brackets)

**Phase 0: Foundations**
- Timeline with AFK trimming + web extension + VS Code plugin. [AFK awareness, Browser tabs]
- Categories + one-time rating of unknown activities: a popup asks "deep / shallow /
  distraction?" and shows openjev's guess (`choice`) if enabled. [App categories, Deep vs.
  shallow, Measure the depth of each activity]
- `aiwa check` prints the timeline with categories.

**Phase 0.5: Classification loop** (decided 2026-09-28)
- Classification table keyed by **domain** for browsers (never the full URL), by app otherwise:
  category, confidence, source (openjev / user / rule), date.
- New domain → ask openjev first (optional, off by default) → cache answer + confidence.
- Confidence below a threshold (default 0.7), openjev off or offline → once the user has
  stayed **15 s** on that domain, popup asks; the answer overrides openjev.
- No global "1 question per 10 min" cap: one popup at a time, the 15 s dwell filters quick
  visits, and "Ask later" backs off per domain.
- Needs a light **5 s poll** of the current window/tab; full analysis stays at 60 s.
- Privacy note: with openjev on, every new tracked domain is sent (domain only).

**Phase 1: Measure (scoreboard)**
- Focus metric (below) in `metrics.py`, `aiwa focus` to inspect it on real data.
- Deep hours = time where 10-min focus intensity ≥ threshold; in the tray; daily score in
  `daily_scores`. [Quality = time × intensity, 4DX 2 lead measures, 4DX 3 scoreboard]
- Report: top activities by deep hours. [Law of the vital few]

### Focus metric
Deep work still involves switching, but within a small set of related items (a
"working sphere", González & Mark 2004). So focus is measured like a cache
(Denning's working set, 1968), over a sliding window of length τ ending at time t:

- **Item** = segment key: app, or app · domain for browsers.
- **Working set**: distinct items in the window; **effective items** = exp(entropy of time
  per item), so a tab glanced at for 2 s barely counts.
- **Hit rate**: a switch is a *hit* if the target was used within the previous τ, a *miss*
  if it is new. hit rate = (hits + 1) / (switches + 1), so no switching counts as 1.
- **Working-set fit** = min(1, capacity / effective items), capacity default 5.
- **Stability** = fit × hit rate (fragmentation = 1 − stability).
- **Deep share** = share of active (non-away) time in deep items.
- **Focus intensity** = deep share × stability, in [0, 1]. Undefined when less than a
  quarter of the window is active.
- Measured at several horizons (default τ = 2, 10, 30 min): short windows show quick
  lookups, long windows show slow drift.

**Phase 2: Protect focus**
- Focus sessions from the tray: duration, allowed categories, goal; sprint mode with
  countdown; grand-gesture mode (long, strict). [Focus sessions, Ritualize, Grand gesture,
  Work like Roosevelt]
- Rules: fragmentation (existing, now session-aware), interruption loops (repeated < 60 s
  visits to shallow apps), "lull → distraction" (short idle then a distraction app).
  [Attention residue, Don't fill every lull]
- `OpenjevDecider` with summarized state; fall back to rules on error, timeout or when disabled.

**Phase 3: Plan the day**
- Morning popup to block the day (deep / shallow / collab / distraction windows); compare
  plan to actual; re-plan anytime. [Schedule every minute, Hub-and-spoke]
- Distraction windows: nudge when distraction apps are used outside them.
  [Breaks from focus, not from distraction]
- Shallow budget % with a tray warning. Slack/mail batching windows; things that come up in
  between go to the small-task inbox. [Shallow-work budget, Become hard to reach]
- Setup preset for depth philosophy (monastic / bimodal / rhythmic / journalistic) that
  fills default plan and strictness. [Choose a depth philosophy]

**Phase 4: Rituals and review**
- Workday end time → shutdown popup (inbox review, park open loops, "done"); silence work
  nudges afterwards; flag late work. [Shutdown ritual, Fixed-schedule productivity, Be lazy]
- Goals (1–2), sessions tagged by goal, weekly review popup with deep hours per goal vs.
  target, plus a per-app "served a goal?" check (openjev `choice`, optional).
  [4DX 1, 4DX 4, Craftsman approach, Don't use the internet to entertain yourself]
- After a long session, suggest a walk with one problem; ask for the outcome afterwards.
  [Productive meditation]

**Phase 5: Experiments**
- 30-day quit test for a chosen app/site: track slips, ask the two questions at the end. [30-day test]

**Docs only:** deep work hypothesis, memory training, making senders do more work, not responding to everything.

## Critical files
- Modify: `src/aiwa/core/collector.py`, `core/analyzer.py`, `core/policy.py`, `core/store.py`,
  `core/rules/__init__.py`, `config.py`, `app.py`, `cli.py`, `ui/tray.py`, `ui/popup.py`
- New: `core/timeline.py`, `categories.py`, `sessions.py`, `metrics.py`, `decider.py`,
  `rules/interruptions.py`, `rules/lull.py`, `ui/plan.py`, `ui/review.py`
- Track progress in `docs/deep-work.md` (update the checkboxes per phase).

## Verification
- Unit tests per module with synthetic timelines (`tests/`), extending `tests/test_core.py`
  style; openjev mocked (no network in tests).
- `aiwa check`: prints timeline, categories, metrics and findings on real ActivityWatch data.
- New `aiwa replay --date YYYY-MM-DD`: replays a real day and lists the nudges that *would*
  have fired, to tune thresholds without being interrupted.
- `scripts/try_openjev.py`-style smoke test for `OpenjevDecider`.
- Manual: run `uv run aiwa start`, walk through each new popup on macOS.


## Decisions 2026-09-28: focus sessions
- Started and **stopped by the user**, no fixed length (a forced period can overwhelm;
  stopping someone mid-flow works against deep work).
- 0–25 min: pokes every minute while focus is low (encouraging; the 25 is never shown).
- 25–50 min: no stop reminders; a dip in focus first asks "is this session done?",
  then pokes every minute if they keep going.
- 50 min+: "time to wrap up", repeated every 2 min until stopped.
- Away 5 min during a session: alarm sound, every minute until back.
- Away 10 min (or the Mac asleep / aiwa not running that long): the session ends by
  itself, as of when the user left (added after a session ran overnight).
- The global "one nudge per 20 min" and "never while away" rules were Claude's
  defaults, not the user's; sessions ignore them. Non-session nudges (fragmentation,
  bouncing) are parked until scheduled deep-work blocks are designed.

**Later:**
- "Low focus" as a **personal quantile** of the user's own history instead of a
  fixed 0.35, so the bar rises as their focus capacity improves (`core/session.py`
  `LowFocus` is the swap point).
- A **full-screen mascot** instead of the popup, so continuing with a distraction
  isn't possible. Popups first, to test the behaviour.


## Decisions 2026-09-29: daily rhythm, tasks, AI
- **Depth philosophies are configuration, not labels.** All four stay on the list;
  **rhythmic** is built first (daily block + chain, done).
- **Evening prompt changes:** instead of "plan tomorrow" (time, task, warm-up), ask
  **"What needs to be done tomorrow?"**; the user lists things freely and aiwa turns
  them into tasks in **its own to-do list**. The block time comes from the rhythm settings.
- **No warm-up reminder** before the block (to be removed from the current version).
- **Tasks come up when a session starts**, one at a time: finish one, get the next.
- **Planning service** (`core/planning.py`, one interface): turn free text into tasks,
  break big tasks into small steps, pick the next task. A rule-based version first;
  an AI version later.
- **AI integration later:** a text-generating model (now Google Gemini 3.5 Flash, 2026-09-29; NVIDIA's hosted models were unresponsive) for
  talking with the user and open tasks: planning, task breakdown, encouragement.
  openjev (multiple choice only) can't do this. Build features behind small
  interfaces so the AI can be swapped in without changing storage or UI flow.
- Agreed next items, in order: evening wind-down pokes (sleep anchor, escalation
  opt-in), gradual shift of the block to the morning, learning daily routines from
  "what was that?" questions after absences, calendar then Jira/Trello integration.

**Open questions:** do unfinished tasks carry over automatically? Split big tasks
by hand before the AI planner exists, or wait for it?


## Decisions 2026-09-29 (later): tasks are an incoming backlog, not a daily plan
- **Input = new incoming tasks**, not a plan for tomorrow. The list grows over time;
  the evening prompt asks "anything new to take care of?", not "plan tomorrow".
- **Entered through a UI** (a minimal Jira-like task list: "+", title, description),
  not a chat prompt. One user, one "life project".
- **Each task needs a deadline and the user's own time estimate.** openjev classifies it
  (deep/shallow) and checks the estimate; the deadline drives urgency.
- **Not atomic** (vague, or longer than one 50-min session) → the user breaks it down
  themselves; the AI suggests possible steps.
- **Productivity, not guilt:** measure work done (tasks finished, deep minutes toward a
  **daily deep-work quota of ~4 hours**), never "tasks left undone".
- **Goal groups:** tasks are grouped by goal (suggested, editable). Each session works on
  one group, chosen by urgency (deadlines) and importance, so the user doesn't switch
  between goals within a session.
- The planning chat built earlier today is superseded by this.


## Decisions 2026-09-29: mornings, consistency, routines, offline work
- **No automatic shift of deep work to the morning.** Instead: **consistency** — sessions
  should start at a similar time every day; the tray shows how consistent they were.
- **Morning start:** when the user first picks up the laptop, show today's work, then
  suggest the morning routine: ask how long it takes; deadline = that time + buffer
  clamp(20% of it, 5, 20) min. Back early (after stepping away) → "finished your routine?":
  finished → "start working?" (yes → session; no → wait for the deadline); "not yet"
  → back to the routine, deadline +1 min. Deadline without a session → alarm until a session starts. "Heading out today" skips it (day shifts, travel; calendar
  integration will later give the leaving time / movement time).
- **Routine learning:** after an absence, ask "what was that?" at random, more likely for
  longer absences (<5 min never; 5–20 min ~20%; 20–60 ~60%; 1–3 h ~80%; >3 h ~50%).
  Taxonomy: body care, food, movement, rest, chores, people, out, offline work, leisure
  (two levels; the popup offers the likely options for the duration and time of day).
  Answers build typical times per routine for later routine prompts.
- **Offline work** counts as deep work only in a session, on a task marked offline
  (openjev suggests, the user confirms): being away is then the work (no away alarm or
  auto-end). Other absences answered "offline work" are only categorized, and may prompt
  a session next time.

Build order: morning start → routine questions → offline tasks → consistency line.

- **Offline tasks (built):** openjev judges each new task "can it be done away from a
  computer?". When a task is handed over in a session, the popup offers "Start offline" /
  "At the computer" (offline first when openjev thinks so); the answer is stored on the
  task. Away on an offline task: no alarm, no auto-end (also across laptop sleep); back →
  the time is recorded as deep minutes ("Offline" in the scoreboard) and aiwa asks whether
  the task is done; no "what was that?" question for that absence. Away longer than the
  estimate + 30 min → only the estimate is credited and the normal away rules apply.
  Absences answered "offline work" outside a session: only recorded, as an insight to
  make use of later (decided 2026-09-29: no session prompt for now).
- **Consistency line (built):** the tray shows "Start time: usually HH:MM · on time N of
  the last 5 days". Usual = median of each day's first session start over 14 days (from 3
  days with a session); on time = within ±30 min; a day without a session is not on time;
  today counts once it has a session.

- **Routine answers (update):** the user will *type* what they did, and openjev classifies
  it into the taxonomy; these questions will move into an inbox-style interface later
  (interfaces come after the data work). The current popup with fixed options is interim.
- **Typed routine answers (built 2026-09-29):** the popup asks "What did you do?" with a
  text field. openjev picks the activity from the taxonomy (one call, 27 activities +
  "none of these"). ≥ 0.7 sure → saved. Unsure → "which one was it?" with its top 3
  guesses, "Something else" and "Don't ask me this" (then openjev's guess is kept, marked
  unsure). The typed text is always kept. The inbox UI comes later.

## Decisions 2026-09-29: capture instead of focus nudges
- **No focus nudges outside sessions.** The daily quota is the pressure; outside sessions
  the user isn't pushed to stay focused. The parked fragmentation/bouncing rules stay off.
- **Capture:** outside sessions, aiwa asks "anything worth noting?":
  - on a shallow app/site (email, chat) after 15 s, once per visit (switching away and
    back is a new visit);
  - after 5 min in distraction (feeds, video; any mix of them; a break of 1+ min ends the
    stretch), once per stretch.
  The user types a note (kept with its source tab/window). openjev judges whether it's a
  to-do; if so, "Add it to your tasks?" opens the task form prefilled (estimate, deadline,
  goal group priority as usual) and the task is linked to its tab/window.
- **Follow-up:** a task from a tab/window not visited for 15 min → "Did you finish it?":
  Done, close the tab/window · Done · Another day, close the tab/window (stays in the
  backlog, its link kept) · Not yet (asked again after 15 min). Closing works for
  Chrome-family browsers and Safari tabs, and app windows that support AppleScript
  (macOS asks once for permission to control that app).
- **Changing a category** belongs in the GUI (later), not the tray.
- **Calendar / Jira / Trello:** undecided. Idea: use existing MCP servers rather than
  building integrations; this starts to overlap with general agent platforms (e.g.
  OpenClaw), so decide the boundary before building.
- **Answers "offline work" outside a session:** an insight to use later.

## Decisions 2026-09-29: shutdown ritual
- **When it's offered** (revised twice 2026-09-29, the user's design): offer when
  time weight × focus weight ≥ 0.5.
  - Time weight: an S-curve (logistic) centred on the shutdown time (18:00 weekdays,
    `[shutdown]`): 16:00 0.01, 17:00 0.1, 17:30 0.25, 18:00 0.5, 18:30 0.75, 19:00 0.9.
  - Focus weight: 1 − (10-min focus / 0.6): high when focus is low, 0 when focused; 1
    with no data.
  - Everything waits until any session is over (offers, the alarm, the ritual's steps).
  - Start shutdown / Later (30 min).
- **Not "reflect right after stopping"** (the user is gone by then). Instead, stats:
  - **Off time** = the peak of the smoothed time-of-day distribution of the starts of
    absences longer than 3 hours (the user stops interacting with the computer), after
    5+ days of data.
  - A session ended by the user within 30 min of the off time → "wrap up the day?"
  - Wrap-up missed on 3+ of the last 5 workdays (aiwa running) → in the 20 min before the
    off time, offer a daily wrap-up alarm (off time − 15 or − 30 min; at most weekly).
    The alarm rings (after any session) until the offer is answered.
- Steps: each of today's unreviewed notes (Make it a task / Keep as note) → "Wrap up
  your day in your own words: anything still open?" (the user wraps up themselves; new
  tasks are rare since capture happens during the day; typed; each answer opens the task form; repeats until
  "That's all") → today's deep work vs. quota, tomorrow's block and first task →
  "Shutdown complete".
- Once started, capture questions stop for the rest of the day, and the 21:30 "anything
  new?" is skipped (it's still asked on non-workdays).

## Decisions 2026-09-29: weekly review (4DX #4)
- Part of the shutdown ritual of the week's last workday (Friday), after the wrap-up;
  missed → at the next shutdown. Outside sessions like everything else.
- Shows: deep work this week and per day, the daily goal reached on N of M workdays,
  deep minutes per goal group (with priority; high-priority groups with none are
  called out), the chain, start-time consistency, last week's answer.
- Then: "Looking at this week: what will you change next week?" (typed; kept and
  shown at the next review).
- Sessions now record their goal group (the group of the last task started in them).

## Decisions 2026-09-29: focus alarm and horizons
- In sessions, "low focus" = the **2-minute** focus score below 0.35 **and not rising**.
  Switching back from a distraction, the 2-min window still echoes the distraction; the
  rising trend (up more than 0.05 vs. ~30 s earlier) shows the user is back → no poke,
  and the alarm stops.
- Deep minutes (scoreboard, quota, shutdown's focus weight) use a **5-minute** window
  (was 10). Horizons: 2 / 5 / 30 min.

## Decisions 2026-09-29: shallow-work budget, and soft thresholds in general
- **Philosophy (the user's):** every limit is a threshold, but the user is relaxed
  around it: measure how far over it they are, and *sample* whether to prompt, more
  likely the further over. No hard trigger at the line.
- Shallow budget: shallow minutes ÷ active minutes today, limit 30% (`[shallow] limit`).
  Checked every 30 min on workdays, outside sessions, before the shutdown, after 1 h at
  the computer. Chance per check = 1 − e^(−overshoot / 0.15): +5 pts 28%, +10 49%,
  +20 74%. Prompt: "Batch the rest for later and get back to deep work?" → Start a focus
  session / Not now.
- Tray: "Shallow today: 1h 40m · 28% (limit 30%)". Weekly review: the week's share.

## Decisions 2026-09-29: productive meditation
- A thinking walk on one well-defined problem. Suggested after a session the user
  stopped with 25+ deep minutes, half of the time (`MeditationParams.chance`); or tray →
  Thinking walk… any time.
- The user types the problem (prefilled with the next task) and picks 15 / 30 / 45 min.
  The walk is a session on an offline "task": away = the work, counted as deep minutes
  (up to its length + 30 min grace, like offline tasks).
- Back → "What did you figure out about …?" → kept as a note (reviewed in the shutdown),
  and the walk's session ends.

## Decisions 2026-09-29: routine reminders
- Usual times per activity = peaks of the smoothed start-time distribution of labelled
  absences, each with 3+ days within ±90 min (several per activity possible: breakfast,
  lunch, dinner). Sleep, toilet and offline tasks are excluded.
- Sampled (soft threshold): every 15 min, if nothing that could be it happened today (an
  absence of 10+ min in the window, labelled as it or unlabelled), chance = share of past
  days on which it had started by now. Outside sessions only.
- "Around 12:30 is usually time for a meal. Time for it now?" → Going now / Later /
  Skip today (Going now and Skip today: no more reminders for it today).
