"""The craftsman approach to tools (Deep Work, rule 3): keep a site or app only if it
clearly helps your core goals more than it costs.

It's about network tools and distractions, not work tools: sites and apps the
user counts as deep work are never asked about. The goal groups stand for the core goals. For each site/app aiwa works out, per week,
the time on it that served a goal (inside a session for that goal) and the time that
served none; a note taken there that became a task counts as having helped. A rule
(time that served nothing, soft threshold) picks sites worth asking about; once per
weekly review the user is asked whether one of them substantially helps a goal. The
answer is remembered, and later reviews show how its time changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aiwa.core.events import Category, Segment
from aiwa.core.rules.base import Rule, RuleParams


@dataclass
class SiteWeek:
    key: str
    minutes: float = 0.0
    served: dict[int, float] = field(default_factory=dict)  # goal group id → minutes in its sessions
    notes_to_tasks: int = 0  # notes taken there that became tasks
    category: Category | None = None  # how it counts (the latest seen)

    @property
    def unserved(self) -> float:
        """Minutes that served no goal (0 if it produced tasks: it was useful input)."""
        return 0.0 if self.notes_to_tasks else self.minutes - sum(self.served.values())


def site_weeks(segments: list[Segment], sessions: list[tuple[datetime, datetime, int | None]],
               notes: list[tuple[str, bool]]) -> dict[str, SiteWeek]:
    """`sessions`: (start, end, goal group); `notes`: (source key, became a task?)."""
    sites: dict[str, SiteWeek] = {}
    for s in segments:
        if s.away:
            continue
        site = sites.setdefault(s.key, SiteWeek(s.key))
        site.minutes += s.duration.total_seconds() / 60
        site.category = s.category or site.category
        for start, end, group in sessions:
            overlap = (min(s.end, end) - max(s.start, start)).total_seconds() / 60
            if group is not None and overlap > 0:
                site.served[group] = site.served.get(group, 0.0) + overlap
    for key, became_task in notes:
        if became_task and key in sites:
            sites[key].notes_to_tasks += 1
    return sites


class WorthAsking(Rule[SiteWeek]):
    """Hours this week that served no goal: 2 h → 50% chance of asking, soft ±30 min."""

    def __init__(self, threshold_hours: float = 2.0, softness_hours: float = 0.5, rng=None):
        super().__init__(RuleParams(threshold=threshold_hours, softness=softness_hours), rng)

    def measure(self, site: SiteWeek) -> float:
        return site.unserved / 60

    def active(self, site: SiteWeek) -> bool:
        return site.category is not Category.DEEP  # work tools aren't what this is about


def pick(sites: dict[str, SiteWeek], judged: set[str], rule: WorthAsking) -> SiteWeek | None:
    """The site to ask about this week: most unserved time first, each sampled by the rule."""
    for site in sorted(sites.values(), key=lambda s: -s.unserved):
        if site.key not in judged and rule.decide(site):
            return site
    return None
