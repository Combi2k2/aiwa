# aiwa: AI watcher

aiwa runs quietly in the background, watches how you work (only in the apps you
choose), and nudges you at good moments: when your focus is fragmenting, when
small tasks are piling up, or when it's time to clear them in one batch.

Everything stays on your machine.

## Requirements

- [ActivityWatch](https://activitywatch.net) installed (it records window activity;
  aiwa reads it through its local API). aiwa starts ActivityWatch's background
  programs itself, so ActivityWatch's own app and menu-bar icon aren't needed
  (set `[activitywatch] manage = false` to run it yourself instead). Add the
  ActivityWatch browser extension for website titles/URLs.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

## Windows (not yet tested)

Download [`scripts/windows/aiwa.bat`](https://github.com/Combi2k2/aiwa/raw/main/scripts/windows/aiwa.bat)
and double-click it. It installs everything aiwa needs (uv, Python, ActivityWatch, aiwa
itself, into your user folder, no admin rights needed), asks once for the optional API
keys, puts an "aiwa" shortcut on the desktop and starts aiwa (its icon is next to the
clock). Run the file again to update. Windows may warn about an unknown file the first
time: "More info" → "Run anyway".

## Usage

```bash
uv sync          # create .venv and install dependencies
uv run aiwa      # start the tray app (settings file is created on first run)
uv run pytest    # run tests
```

The menu-bar icon is a scope whose ring fills toward today's deep-work goal
(a dot in the middle once reached). The tray menu shows today's scoreboard:
deep minutes, streaks, goal progress and time per activity.

**Focus sessions** (tray → Start focus session) run until you stop them. aiwa
pokes you when your focus slips (with an alarm that rings until you're focused again), asks whether you're done if focus drops later
on, reminds you to wrap up after 50 minutes, and sounds an alarm if you're away
for 5 minutes (it keeps ringing until you're back; choose your own sound with
`alarm_sound` in the settings). Details in `docs/plan.md`.

**A daily deep-work block** (Deep Work's "rhythmic" style) at the same time every
day (weekdays 09:00 by default, `[rhythm]`), with a **chain** of days you kept it.

**Your task backlog** (tray → Tasks… / New task…): tasks come in over time, each with a
deadline, your own estimate and a goal group. openjev checks each one; anything vague
or longer than one 50-minute session is broken down (by you, with suggested steps from
Gemini when it's available). Each focus session works on one goal group, the most
urgent one (work left vs. deadlines, weighted by the group's priority), and hands over
its tasks one at a time. In the evening aiwa asks whether anything new came up.

The goal is a **daily deep-work quota** (4 h to start, up to 10 h): the scope's ring
fills toward it, and aiwa shows what you did, never what's left.

**A morning start**: when you first pick up the laptop, aiwa shows today's work and asks
how long your morning routine takes. Back early? It asks whether you're finished ("not yet"
sends you back with a minute more). When the routine time (plus a small buffer) is over without a
session, the alarm rings until you start one. "Heading out today" skips it.

**An evening wind-down**, every night: from 22:00 a reminder every 5 minutes while you're
still at the computer ("10 more minutes" once per night, or lock the screen), and from
00:00 the alarm rings until you lock the screen or step away. The tray shows when you
stopped last night and started this morning. Settings under `[bedtime]`.

**Routines**: after you've been away (or the laptop slept), aiwa sometimes asks what it
was: a meal, a shower, sport… More often for longer absences, never for short ones;
overnight is logged as sleep. This builds up your typical times for later reminders.

Everything else is in the tray menu: rate your focus,
snoozing nudges, **Open settings…** (the config file) and **Start at login**.

Developer tools for inspecting the data processing: `uv run aiwa --help`
(`check`, `focus`, `calibrate`, `track`, `categorize`, ...).

Only tracked apps are recorded by name. Other windows are seen only as
`(untracked)`: switches still count, but no names or titles are kept.

When you use an untracked app for 5 seconds, aiwa asks whether to track it,
and as what (Deep / Shallow / Distraction / Neutral / Don't track / Ask later).
The name is only shown in that popup; it is never sent anywhere, and
"Don't track" stores just a hash of it. Apps can
also be listed in `[[track]]` in the config.

## Categories

Every activity counts as **deep**, **shallow**, **distraction** or **neutral**
(from *Deep Work*). `[[category]]` rules in the config are checked first. For
any other tracked app or website, aiwa asks once in a popup and remembers
the answer. Browsers are classified per website domain, never as a whole.

With `[openjev] enabled = true` and `OPENJEV_API_KEY` set (environment, or a
`.env` next to the config), each new tracked app or website is sent to openjev
after 2 s on it. A confident answer is shown for you to confirm or change; if
openjev is less than `min_confidence` sure (or off), you're asked after 10 s,
with its guess shown. Only the app name or website domain is sent, e.g.
`github.com`. Your answer always overrides openjev's.

## Focus intensity

Deep work still involves switching, but between a few related things (editor,
docs, terminal), not endlessly to new ones, and not every few seconds. Over a
sliding window, aiwa scores

    intensity = depth × working-set fit × hit rate × continuity    (0 to 1)

at several window sizes (default 2, 10, 30 min), and summarizes periods as
deep minutes, longest deep streak and distraction switches per hour. Every
component and parameter is described in `docs/components.md`.

## Layout

```
src/
  cli.py          entry point: starts the tray app; subcommands are developer tools
  commands/       one module per developer tool (check, focus, calibrate, ...)
  config.py       settings + app/window allowlist (TOML)
  app.py          the daemon: 2 s classification poll + 15 s analysis → UI
  core/           OS-independent logic
    scoreboard/   per-minute ledger, day summary, keeper (today's score)
    collector.py  reads window, AFK and browser-tab data from ActivityWatch
    timeline.py   cuts out away time, attaches tabs, merges repeated segments
    categories.py deep / shallow / distraction / neutral, and masking untracked apps
    classifier.py when to ask: track? classify? confirm openjev's answer?
    openjev.py    optional category suggestions
    focus/        focus intensity: window, depth, stability, continuity, moment, period, params
    analyzer.py   runs rules over recent events
    rules/        one file per pattern (fragmentation, ...)
    policy.py     when a nudge may interrupt (gaps, snooze)
    store.py      SQLite: nudge history, small-task inbox, remembered categories
  ui/             PySide6 (Qt): tray, popup, inbox; same on every OS
  services/       background programs aiwa runs: ActivityWatch's server and watchers
  platforms/      the only OS-specific code: start at login, ActivityWatch location
    macos.py      LaunchAgent
    windows.py    registry Run key (untested)
    linux.py      XDG autostart (untested)
```

## Adding a rule

Create `rules/<name>.py` with a class that has a `name` and a
`check(segments, now) -> Finding | None` method, then add it to
`default_rules()` in `rules/__init__.py`.

## Platform status

| | macOS | Windows | Linux X11 | Linux Wayland |
|---|---|---|---|---|
| Tested | yes | not yet | not yet | not yet |
| Window tracking | ✅ | ✅ | ✅ | needs `awatcher` |
| Popups | ✅ | ✅ | ✅ | position not controllable |
