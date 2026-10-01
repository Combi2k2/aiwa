"""Rules: a measured quantity against a soft threshold (base.py), one module per rule.

    base.py        Rule, RuleParams, AllOf, Cadence
    budget.py      shallow-work budget
    shutdown.py    when to offer the shutdown: time of day × low focus
    focus.py       low focus in a session (and not rising)
    absence.py     whether to ask "what did you do?" about an absence
    reminder.py    routine reminders
    capture.py     time on shallow work / in distraction before "anything worth noting?"
    walk.py        whether to suggest a thinking walk after a session

fragmentation.py is an older kind of rule (segments → Finding, run by core/analyzer.py),
parked since focus sessions took over; it would move onto `Rule` when it's used again.
"""

from aiwa.core.analyzer import Rule as PatternRule
from aiwa.core.rules.fragmentation import Fragmentation


def default_rules() -> list[PatternRule]:
    # Nudges outside focus sessions are parked until scheduled deep-work blocks
    # are designed (Deep Work: schedule deep work instead of catching it randomly).
    # Fragmentation stays available but is not active.
    return []


__all__ = ["Fragmentation", "default_rules"]
