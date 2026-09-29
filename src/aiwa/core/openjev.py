"""Optional client for the openjev structured-decision API.

Free at the time of writing, but with no published privacy policy, so only
short summaries are ever sent: an app name or a website domain (e.g. "github.com").
"""

from __future__ import annotations

import requests

from aiwa.core.events import Category

URL = "https://api.openjev.sh/v1/systemone"

CATEGORY_CRITERIA = {
    Category.DEEP.value: "Cognitively demanding work that creates value and is hard to replicate: coding, writing, design, research, analysis",
    Category.SHALLOW.value: "Logistical or communication work that is easy to replicate: email, chat, scheduling, admin",
    Category.DISTRACTION.value: "Entertainment, news or social media unrelated to work",
    Category.NEUTRAL.value: "System utilities or tools that are neither: settings, file manager, music player, terminal housekeeping",
}


class Openjev:
    def __init__(self, api_key: str, timeout: float = 5):
        self.api_key = api_key
        self.timeout = timeout

    def ask(self, state: str, questions: dict) -> dict:
        response = requests.post(
            URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": "openjev", "state": state, "questions": questions},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["answers"]

    def suggest_category(self, activity: str) -> tuple[Category, float] | None:
        """Best-guess category and its probability, or None if the call fails."""
        try:
            answer = self.ask(
                f"A person spends time on this computer activity: {activity}",
                {
                    "category": {
                        "type": "choice",
                        "instructions": "How should this activity be classified for focus tracking?",
                        "criteria": CATEGORY_CRITERIA,
                    }
                },
            )["category"]
            choice = answer["choice"]
            return Category(choice), float(answer.get("probabilities", {}).get(choice, 0))
        except (requests.RequestException, KeyError, ValueError):
            return None


SIZE_MINUTES = {"under_25": 15, "25_to_50": 40, "50_to_120": 85, "over_120": 150, "unclear": None}

TASK_QUESTIONS = {
    "kind": {
        "type": "choice",
        "instructions": "What kind of work is this task?",
        "criteria": {
            "deep": "Cognitively demanding: writing, coding, designing, studying, analysing",
            "shallow": "Logistics or communication: email, messages, scheduling, admin, errands",
        },
    },
    "size": {
        "type": "choice",
        "instructions": "How long will this task take one focused person?",
        "criteria": {
            "under_25": "Under 25 minutes",
            "25_to_50": "25 to 50 minutes",
            "50_to_120": "Between 50 minutes and 2 hours",
            "over_120": "More than 2 hours",
            "unclear": "Impossible to tell: the task is too vague or depends on context not given",
        },
    },
    "specific": {
        "type": "noul",
        "instructions": "Is the task specific enough that someone could estimate its size and know when it is done?",
        "criteria": {"true": "Concrete scope and a clear end point", "false": "Vague, open-ended, or needs context that is not given"},
    },
    "offline": {
        "type": "noul",
        "instructions": "Can this task be done well away from a computer (e.g. reading on paper, writing or solving by hand, thinking it through on a walk)?",
        "criteria": {"true": "Needs no computer", "false": "Needs a computer or phone"},
    },
}


def assess_task(client: Openjev, task: str):
    """Kind, estimated minutes and specificity of a task, or None if the call fails."""
    from aiwa.core.backlog import Assessment

    try:
        a = client.ask(f'A person\'s task: "{task}"', TASK_QUESTIONS)
        return Assessment(
            kind=a["kind"]["choice"],
            minutes=SIZE_MINUTES.get(a["size"]["choice"]),
            specific=float(a["specific"]["noul"]),
            offline=float(a["offline"]["noul"]) if "offline" in a else None,
        )
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def suggest_group(client: Openjev, task: str, groups: list[str]) -> str | None:
    """The name of the existing goal group this task belongs to, or None (a new goal, or failure)."""
    if not groups:
        return None
    criteria = {f"g{i}": f"Part of the goal \"{name}\"" for i, name in enumerate(groups)}
    criteria["new"] = "Belongs to none of these goals"
    try:
        a = client.ask(
            f'A person\'s new task: "{task}"',
            {"group": {"type": "choice", "instructions": "Which of the person's goals does this task belong to?",
                       "criteria": criteria}},
        )["group"]
        choice = a["choice"]
        return groups[int(choice[1:])] if choice.startswith("g") and a.get("confidence", 1) >= 0.5 else None
    except (requests.RequestException, KeyError, ValueError, TypeError, IndexError):
        return None
