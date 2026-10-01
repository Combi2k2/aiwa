"""The scoreboard: what today (and past days) looked like, minute by minute.

    ledger.py   one entry per minute: focus intensity + what you mostly did  (the data)
    day.py      a day's summary from those entries: deep minutes, streaks,
                time per activity, progress toward the daily goal           (the numbers)
    keeper.py   scores new minutes as time passes and saves them; today()   (the glue)

All are UI-independent: the tray, developer tools and a later GUI read the same data.
"""

from aiwa.core.scoreboard.day import DayScore, day_bounds, summarize_day
from aiwa.core.scoreboard.keeper import ScoreKeeper
from aiwa.core.scoreboard.ledger import MinuteEntry, score_minutes

__all__ = ["DayScore", "MinuteEntry", "ScoreKeeper", "day_bounds", "score_minutes", "summarize_day"]
