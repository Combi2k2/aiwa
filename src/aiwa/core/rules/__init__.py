from aiwa.core.analyzer import Rule
from aiwa.core.rules.fragmentation import Fragmentation


def default_rules() -> list[Rule]:
    return [Fragmentation()]
