"""One module per `aiwa` command. `cli.py` only parses arguments and dispatches here.

    data.py        shared: load categorized segments for a time range
    check.py       aiwa check
    focus.py       aiwa focus [--span N | --date YYYY-MM-DD]
    calibrate.py   aiwa calibrate
    track.py       aiwa track / untrack
    categorize.py  aiwa categorize
    autostart.py   aiwa autostart install|uninstall|status
"""
