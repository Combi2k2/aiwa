from aiwa.core.analyzer import Rule
from aiwa.core.rules.fragmentation import Fragmentation


def default_rules() -> list[Rule]:
    # Nudges outside focus sessions are parked until scheduled deep-work blocks
    # are designed (Deep Work: schedule deep work instead of catching it randomly).
    # Fragmentation stays available but is not active.
    return []
