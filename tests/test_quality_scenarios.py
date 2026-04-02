from __future__ import annotations

from chatops.evaluation.harness import load_quality_scenarios


def test_quality_suite_uses_at_least_30_realistic_scenarios() -> None:
    scenarios = load_quality_scenarios()
    assert len(scenarios) >= 30
