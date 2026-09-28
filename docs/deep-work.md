# Deep Work → aiwa

Every idea from Cal Newport's *Deep Work*, with a first idea for how aiwa could
support it. We design and build these one at a time; each `→` line is a
starting point to refine, not a decision.

Status: `[ ]` not started · `[~]` designing/building · `[x]` done

## Foundations (needed by many items below)

- [x] **AFK awareness**: read ActivityWatch's AFK bucket; drop away time; never nudge while away
- [x] **Browser tabs**: use the ActivityWatch web extension for tab URL/title
- [x] **App categories**: user labels apps/sites as deep, shallow or distraction
- [ ] **Focus sessions**: explicit "start focus" with a length and allowed apps
- [ ] **Input intensity** (optional): `aw-watcher-input` counts to tell working from idling

## Core ideas

- [x] **Deep vs. shallow work**
  → classify every stretch of activity as deep or shallow (via categories + sessions)
- [ ] **Deep work hypothesis** (valuable, rare, meaningful)
  → onboarding/weekly message framing why the numbers matter; no feature on its own
- [~] **Quality = time × intensity**
  → score blocks by length *and* lack of interruptions, not just time spent
- [~] **Attention residue**
  → fragmentation rule exists; add interruption loops (repeated short visits to Slack/mail)

## Rule 1: Work deeply

- [ ] **Choose a depth philosophy** (monastic, bimodal, rhythmic, journalistic)
  → setup choice that sets the defaults for scheduling and nudge strictness
- [ ] **Ritualize**: where, how long, how you work, what supports you
  → focus-session template: duration, allowed apps, pre-session checklist
- [ ] **Grand gesture**
  → optional "big session" mode: long block, strict allowlist, all nudges but blockers off
- [ ] **Hub-and-spoke collaboration**
  → separate "collaboration" and "solo" blocks; don't nudge about Slack during collaboration
- [ ] **4DX 1: Focus on the wildly important**
  → user sets 1–2 goals; sessions are tagged with the goal they serve
- [ ] **4DX 2: Act on lead measures**
  → track deep hours per goal (a lead measure), not outcomes
- [ ] **4DX 3: Keep a compelling scoreboard**
  → tray shows today's deep hours; simple daily/weekly chart
- [ ] **4DX 4: Cadence of accountability**
  → weekly review popup: deep hours vs. goal, what helped, what got in the way
- [ ] **Be lazy (real downtime)**
  → after the workday ends, stop work nudges; flag work apps opened late in the evening
- [ ] **Shutdown ritual**
  → end-of-day popup: review inbox, park open loops for tomorrow, say "done"

## Rule 2: Embrace boredom

- [ ] **Breaks from focus, not from distraction**
  → user schedules internet/distraction blocks; nudge when distraction apps are used outside them
- [ ] **Don't fill every lull**
  → detect "short idle → distraction app" pattern; gentle check-in, not a block
- [ ] **Work like Roosevelt** (short, intense deadlines)
  → "sprint" session: user picks a task and a tight deadline; countdown in tray
- [ ] **Productive meditation**
  → after a long session, suggest a walk with one problem to think about; ask for the result afterwards
- [ ] **Memory training**
  → out of scope for aiwa; mention in docs only

## Rule 3: Quit social media

- [ ] **Craftsman approach to tools**
  → weekly report per app/site: time spent vs. whether the user marked it as serving a goal
- [ ] **Law of the vital few**
  → show which few activities produce most of the deep hours
- [ ] **30-day test**
  → user picks a service to quit for 30 days; aiwa tracks slips and asks the two questions at the end
- [ ] **Don't use the internet to entertain yourself**
  → evening/weekend report of entertainment browsing; optional planned-leisure prompt

## Rule 4: Drain the shallows

- [ ] **Schedule every minute**
  → morning planning popup with time blocks; compare plan vs. actual, allow re-planning
- [x] **Measure the depth of each activity**
  → ask the user to rate unknown activities once ("how long to train a graduate to do this?")
- [ ] **Shallow-work budget**
  → user sets a percentage; tray warns when shallow time exceeds it
- [ ] **Fixed-schedule productivity**
  → user sets a workday end; shutdown ritual triggers then
- [ ] **Become hard to reach**
  → batch Slack/mail into scheduled windows; small-task inbox collects what comes up in between
- [ ] **Make senders do more work / process-centric email**
  → out of aiwa's reach (no email access); tips in docs only
- [ ] **Don't respond to everything**
  → out of scope; docs only
