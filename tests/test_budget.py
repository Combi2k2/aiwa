import random
from datetime import datetime, timedelta, timezone

from aiwa.core.budget import BudgetParams, ShallowBudget, ShallowShare, prompt_probability, shallow_share

T0 = datetime(2026, 9, 30, 14, tzinfo=timezone.utc)
P = BudgetParams()


def test_share_of_active_time():
    s = shallow_share({"deep": 120, "shallow": 90, "distraction": 30, "neutral": 60, "away": 200})
    assert (s.shallow, s.active, s.share) == (90, 300, 0.3)


def test_probability_grows_with_the_overshoot():
    assert prompt_probability(0.29, P) == 0 and prompt_probability(0.30, P) == 0
    assert round(prompt_probability(0.35, P), 2) == 0.28
    assert round(prompt_probability(0.40, P), 2) == 0.49
    assert round(prompt_probability(0.50, P), 2) == 0.74


def test_checks_are_spaced_and_sampled():
    budget = ShallowBudget(rng=random.Random(3))
    over = ShallowShare(shallow=120, active=300)  # 40%: about half the checks
    assert not budget.should_prompt(T0, ShallowShare(20, 50))  # under an hour at the computer: too early
    results = [budget.should_prompt(T0 + timedelta(minutes=m), over) for m in range(0, 3000)]
    checks = 3000 // 30
    assert 0.35 * checks < sum(results) < 0.65 * checks
