# aiwa: AI watcher

aiwa runs quietly in the background, watches how you work (only in the apps you
choose), and nudges you at good moments: when your focus is fragmenting, when
small tasks are piling up, or when it's time to clear them in one batch.

Everything stays on your machine.

## Requirements

- [ActivityWatch](https://activitywatch.net) running (it records window activity;
  aiwa reads it through its local API). Add the browser extension for tab titles/URLs.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

## Usage

```bash
uv sync                          # create .venv and install dependencies
uv run aiwa config               # print the config path (created on first run)
uv run aiwa check                # recent activity with categories, and findings
uv run aiwa focus                # focus intensity now + last hour, per window size
uv run aiwa focus --date 2026-09-28   # replay a whole day hour by hour
uv run aiwa track                # list tracked apps (track APP / untrack APP)
uv run aiwa categorize           # list remembered categories
uv run aiwa categorize "Slack" shallow   # set one
uv run aiwa start                # run the tray app in the foreground
uv run aiwa autostart install    # start aiwa at login (uninstall | status)
uv run pytest                    # run tests
```

Only tracked apps are recorded by name. Other windows are seen only as
`(untracked)`: switches still count, but no names or titles are kept.

When you use an untracked app for 5 seconds, aiwa asks whether to track it,
and as what (Deep / Shallow / Distraction / Neutral / Don't track / Ask later).
The name is only shown in that popup; it is never sent anywhere, and
"Don't track" stores just a hash of it. Apps can
also be listed in `[[track]]` in the config, or managed with
`aiwa track`, `aiwa track APP` and `aiwa untrack APP`.

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
src/aiwa/
  cli.py          parses arguments, dispatches to commands/
  commands/       one module per command (check, focus, track, ...); data.py loads segments
  config.py       settings + app/window allowlist (TOML)
  app.py          the daemon: 2 s classification poll + 15 s analysis → UI
  core/           OS-independent logic
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
  platforms/      the only OS-specific code: start at login
    macos.py      LaunchAgent
    windows.py    registry Run key (untested)
    linux.py      XDG autostart (untested)
```

## Adding a rule

Create `core/rules/<name>.py` with a class that has a `name` and a
`check(segments, now) -> Finding | None` method, then add it to
`default_rules()` in `core/rules/__init__.py`.

## Platform status

| | macOS | Windows | Linux X11 | Linux Wayland |
|---|---|---|---|---|
| Tested | yes | not yet | not yet | not yet |
| Window tracking | ✅ | ✅ | ✅ | needs `awatcher` |
| Popups | ✅ | ✅ | ✅ | position not controllable |
