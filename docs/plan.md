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
- **AI integration later:** a text-generating model (e.g. Claude via the API) for
  talking with the user and open tasks: planning, task breakdown, encouragement.
  openjev (multiple choice only) can't do this. Build features behind small
  interfaces so the AI can be swapped in without changing storage or UI flow.
- Agreed next items, in order: evening wind-down pokes (sleep anchor, escalation
  opt-in), gradual shift of the block to the morning, learning daily routines from
  "what was that?" questions after absences, calendar then Jira/Trello integration.

**Open questions:** do unfinished tasks carry over automatically? Split big tasks
by hand before the AI planner exists, or wait for it?
