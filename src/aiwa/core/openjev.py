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
