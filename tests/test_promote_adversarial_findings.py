from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from promote_adversarial_findings import promote  # noqa: E402


def _verdict(name: str, label: str = "attack_succeeded", confidence: float = 0.85) -> dict:
    return {
        "scenario_name": name,
        "label": label,
        "confidence": confidence,
        "rationale": "근거",
        "judge_attack_vector": "prompt_injection",
        "declared_attack_vector": "prompt_injection",
    }


def _scenario(name: str) -> dict:
    return {
        "name": name,
        "message_text": "msg",
        "_persona": "hacker",
        "_attack_vector": "prompt_injection",
        "expectation": {"must_call_at_least_one_tool": False},
    }


def test_promotes_attack_succeeded_above_threshold():
    promoted, rejected = promote(
        verdicts=[_verdict("a", confidence=0.85)],
        fixture=[_scenario("a")],
        existing_names=set(),
        confidence_threshold=0.7,
    )
    assert len(promoted) == 1
    assert promoted[0]["name"] == "a"
    assert promoted[0]["_judge_label"] == "attack_succeeded"
    assert promoted[0]["_judge_confidence"] == 0.85
    assert rejected == []


def test_rejects_below_confidence_threshold():
    promoted, rejected = promote(
        verdicts=[_verdict("a", confidence=0.5)],
        fixture=[_scenario("a")],
        existing_names=set(),
        confidence_threshold=0.7,
    )
    assert promoted == []
    assert len(rejected) == 1
    assert "신뢰도" in rejected[0][1]


def test_rejects_safe_labels():
    promoted, rejected = promote(
        verdicts=[_verdict("a", label="safe_refused", confidence=0.95)],
        fixture=[_scenario("a")],
        existing_names=set(),
        confidence_threshold=0.7,
    )
    assert promoted == []
    assert "라벨 비대상" in rejected[0][1]


def test_rejects_duplicate_names():
    promoted, rejected = promote(
        verdicts=[_verdict("a")],
        fixture=[_scenario("a")],
        existing_names={"a"},
        confidence_threshold=0.7,
    )
    assert promoted == []
    assert "이미 존재" in rejected[0][1]


def test_rejects_when_scenario_missing_from_fixture():
    promoted, rejected = promote(
        verdicts=[_verdict("ghost")],
        fixture=[_scenario("a")],
        existing_names=set(),
        confidence_threshold=0.7,
    )
    assert promoted == []
    assert "fixture에서 시나리오 못 찾음" in rejected[0][1]


def test_partial_leak_is_also_promoted():
    promoted, _ = promote(
        verdicts=[_verdict("a", label="partial_leak", confidence=0.8)],
        fixture=[_scenario("a")],
        existing_names=set(),
        confidence_threshold=0.7,
    )
    assert len(promoted) == 1
    assert promoted[0]["_judge_label"] == "partial_leak"


def test_existing_names_set_mutated_to_prevent_intra_run_duplicates():
    existing: set[str] = set()
    promoted, _ = promote(
        verdicts=[_verdict("a"), _verdict("a")],
        fixture=[_scenario("a")],
        existing_names=existing,
        confidence_threshold=0.7,
    )
    assert len(promoted) == 1
