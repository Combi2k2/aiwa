"""The conversational AI for planning (NVIDIA's hosted models via langchain).

It only helps the user put *their own* plan into words: splitting a list into
tasks, asking one short question about a task that is vague or too big, and
turning the answer into steps. It never invents tasks. Every call has a time
limit; on any failure it returns None and the planning falls back to templates.
After a failure the AI is skipped for a while, so a service that's down doesn't
make the user wait for a timeout on every message.
"""

from __future__ import annotations

import json
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

SYSTEM = (
    "You are the planning assistant inside aiwa, a focus app. You help the user put their own plan "
    "into words as small tasks, each doable in one focus session (under 50 minutes). Rules: never "
    "invent tasks or decide for the user; keep the user's own wording; be brief and warm; plain "
    "text, no markdown."
)

REASONS = {
    "vague": "too vague to estimate (unclear scope or end point, or it needs context you don't have)",
    "too_long": "probably longer than one 50-minute focus session",
}


@dataclass(frozen=True)
class AISettings:
    model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    timeout: float = 30.0  # seconds; after this the templates take over
    thinking: bool = True
    retry_after: float = 300.0  # after a failure, skip the AI for this many seconds


class PlanningWriter:
    """Implements planning.Writer with an NVIDIA-hosted chat model."""

    def __init__(self, api_key: str, settings: AISettings):
        from langchain_nvidia_ai_endpoints import ChatNVIDIA  # imported only when the AI is used

        self.settings = settings
        extra = {"reasoning_budget": 1024} if settings.thinking else {}
        with warnings.catch_warnings():  # langchain warns about model kwargs it passes through as-is
            warnings.simplefilter("ignore")
            self.client = self._client(ChatNVIDIA, api_key, settings, extra)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.skip_until = 0.0  # monotonic time; the AI failed recently

    @staticmethod
    def _client(ChatNVIDIA, api_key: str, settings: AISettings, extra: dict):
        return ChatNVIDIA(
            model=settings.model,
            api_key=api_key,
            temperature=0.6,
            top_p=0.95,
            max_completion_tokens=2048,
            chat_template_kwargs={"enable_thinking": settings.thinking},
            **extra,
        )

    def split(self, text: str) -> list[str] | None:
        return _json_list(self._ask(
            "Split this into separate to-do items. Keep the user's wording; don't add, merge or drop "
            f"anything. Reply with only a JSON array of strings.\n\n{text}"
        ))

    def question(self, task: str, reason: str) -> str | None:
        return self._ask(
            f"The user's to-do item: “{task}”. It is {REASONS.get(reason, reason)}. Ask ONE short, "
            "specific question that helps them break it into concrete steps of under 50 minutes each "
            "(for example which part, or how much). Say they can answer with steps, one per line, or "
            "type “keep” to leave it as it is. Reply with the question only."
        )

    def refine(self, task: str, question: str, answer: str) -> list[str] | None:
        return _json_list(self._ask(
            f"To-do item: “{task}”\nYou asked: {question}\nThe user answered: {answer}\n\n"
            "Turn the answer into to-do items in the user's own words, each one concrete step. If the "
            "answer only adds detail, return the item rewritten with that detail. Don't add steps the "
            "user didn't mention. Reply with only a JSON array of strings."
        ))

    def _invoke(self, messages):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.client.invoke(messages)

    def _ask(self, prompt: str) -> str | None:
        if time.monotonic() < self.skip_until:
            return None  # failed recently: don't make the user wait for another timeout
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        future = self.pool.submit(self._invoke, messages)
        try:
            content = future.result(timeout=self.settings.timeout).content
        except (FutureTimeout, Exception):  # a late answer keeps running in the background and is ignored
            self.skip_until = time.monotonic() + self.settings.retry_after
            return None
        content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
        return content or None


def _json_list(text: str | None) -> list[str] | None:
    if not text:
        return None
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        items = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    items = [str(i).strip() for i in items if str(i).strip()]
    return items or None
