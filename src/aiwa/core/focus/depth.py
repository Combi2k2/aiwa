"""Depth: how deep the work in a window was.

    depth = Σ weight(category) × time / Σ time      (neutral time left out of both sums)

Deep counts 1, shallow partly, distraction and unclassified 0 (see params.py).
Neutral items (music player, settings, file manager) don't count for or
against you. None when the window has only neutral time.
"""

from __future__ import annotations

from aiwa.core.events import Category
from aiwa.core.focus.params import FocusParams
from aiwa.core.focus.window import Window


def depth(window: Window, params: FocusParams) -> float | None:
    weighted = counted = 0.0
    for stretch in window.stretches:
        if stretch.category is Category.NEUTRAL:
            continue
        weighted += params.weights.get(stretch.category, 0.0) * stretch.seconds
        counted += stretch.seconds
    return weighted / counted if counted else None
