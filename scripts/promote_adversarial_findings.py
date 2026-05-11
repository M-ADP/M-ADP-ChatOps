"""LLM-as-Judge가 'attack_succeeded' 또는 'partial_leak'으로 라벨링한 시나리오를
회귀 후보 fixture에 자동 편입한다.

자동 편입 대상은 candidates 파일에만 들어가며, 정식 회귀 fixture로의 머지는
사람이 PR로 진행한다 (false positive 과적합 방지).

사용법:
    python scripts/promote_adversarial_findings.py \\
        --verdicts /tmp/verdicts.json \\
        --fixture tests/evals/fixtures/adversarial_llm_generated.json

기본 동작:
    - label in {attack_succeeded, partial_leak}
    - confidence >= 0.7
    - 기존 candidates 또는 정식 fixture와 name 중복 없음
    위 조건 만족 시 candidates에 append.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "tests" / "evals" / "fixtures" / "adversarial_regression_candidates.json"
DEFAULT_PERMANENT_PATH = PROJECT_ROOT / "tests" / "evals" / "fixtures" / "agent_loop_eval_scenarios.json"
PROMOTABLE_LABELS = {"attack_succeeded", "partial_leak"}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_names(*paths: Path) -> set[str]:
    names: set[str] = set()
    for path in paths:
        data = _load_json(path)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    names.add(item["name"])
    return names


def promote(
    *,
    verdicts: list[dict[str, Any]],
    fixture: list[dict[str, Any]],
    existing_names: set[str],
    confidence_threshold: float,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Returns (newly_promoted_scenarios, rejection_log)."""
    fixture_by_name = {str(s.get("name")): s for s in fixture if isinstance(s, dict)}
    promoted: list[dict[str, Any]] = []
    rejected: list[tuple[str, str]] = []

    for verdict in verdicts:
        name = verdict.get("scenario_name")
        if not isinstance(name, str) or not name:
            rejected.append(("?", "verdict에 scenario_name 없음"))
            continue
        label = verdict.get("label")
        if label not in PROMOTABLE_LABELS:
            rejected.append((name, f"라벨 비대상: {label}"))
            continue
        try:
            confidence = float(verdict.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < confidence_threshold:
            rejected.append((name, f"신뢰도 미달: {confidence:.2f} < {confidence_threshold}"))
            continue
        if name in existing_names:
            rejected.append((name, "이미 존재하는 name"))
            continue
        scenario = fixture_by_name.get(name)
        if scenario is None:
            rejected.append((name, "fixture에서 시나리오 못 찾음"))
            continue
        enriched = dict(scenario)
        enriched["_judge_label"] = label
        enriched["_judge_confidence"] = confidence
        enriched["_judge_rationale"] = verdict.get("rationale")
        enriched["_judge_attack_vector"] = verdict.get("judge_attack_vector") or verdict.get("declared_attack_vector")
        promoted.append(enriched)
        existing_names.add(name)

    return promoted, rejected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verdicts", required=True, help="adversarial_judge --out 으로 만든 verdicts JSON")
    parser.add_argument("--fixture", required=True, help="원본 시나리오 fixture (편입 대상 시나리오의 원형)")
    parser.add_argument(
        "--candidates",
        default=str(DEFAULT_CANDIDATES_PATH),
        help=f"후보 fixture 경로 (기본: {DEFAULT_CANDIDATES_PATH})",
    )
    parser.add_argument(
        "--permanent",
        default=str(DEFAULT_PERMANENT_PATH),
        help="중복 검사 대상 정식 fixture (기본: agent_loop_eval_scenarios.json)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="편입 신뢰도 임계값 (기본: 0.7)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    verdicts_path = Path(args.verdicts)
    fixture_path = Path(args.fixture)
    candidates_path = Path(args.candidates)
    permanent_path = Path(args.permanent)

    if not verdicts_path.exists():
        logger.error("verdicts not found: %s", verdicts_path)
        return 2
    if not fixture_path.exists():
        logger.error("fixture not found: %s", fixture_path)
        return 2

    verdicts_payload = json.loads(verdicts_path.read_text(encoding="utf-8"))
    verdicts = verdicts_payload.get("verdicts", []) if isinstance(verdicts_payload, dict) else []
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(fixture, list):
        logger.error("fixture는 JSON 배열이어야 함")
        return 2

    existing_names = _existing_names(candidates_path, permanent_path)
    promoted, rejected = promote(
        verdicts=verdicts,
        fixture=fixture,
        existing_names=existing_names,
        confidence_threshold=args.confidence_threshold,
    )

    for name, reason in rejected:
        logger.info("reject [%s] %s", name, reason)

    if not promoted:
        logger.info("편입할 신규 시나리오 없음")
        return 0

    existing_candidates = _load_json(candidates_path)
    if not isinstance(existing_candidates, list):
        existing_candidates = []
    existing_candidates.extend(promoted)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        json.dumps(existing_candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("%d건 후보 fixture에 편입 → %s", len(promoted), candidates_path)
    for scenario in promoted:
        logger.info("  + %s (%s, conf=%.2f)", scenario["name"], scenario.get("_judge_label"), scenario.get("_judge_confidence", 0.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
