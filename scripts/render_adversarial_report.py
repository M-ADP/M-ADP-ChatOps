"""적대적 평가 결과를 사람이 읽을 수 있는 마크다운 리포트로 렌더링한다.

입력: run_agent_eval --json-out 의 augmented 리포트 + adversarial_judge 의 verdicts
출력: claudedocs/adversarial_eval/<YYYY-MM-DD>.md
     (선택) $GITHUB_STEP_SUMMARY 가 정의돼 있으면 동일 마크다운을 거기에도 append

리포트 구성:
- 요약 카드 (총 시나리오, 라벨 분포, 페르소나 분포)
- 벡터 × 라벨 매트릭스
- 신규 발견 취약점 목록 (회귀 후보 표시)
- 트렌드 (최근 N회 리포트 메타데이터 기반 mermaid 라인 차트)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "claudedocs" / "adversarial_eval"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "tests" / "evals" / "fixtures" / "adversarial_regression_candidates.json"
LABEL_ORDER = ("safe_refused", "safe_clarified", "partial_leak", "attack_succeeded", "ambiguous")
ATTACK_LABELS = {"partial_leak", "attack_succeeded"}


def _render_summary(report: dict[str, Any], verdicts: list[dict[str, Any]]) -> str:
    total = report.get("total_cases", 0)
    label_counts = Counter(v.get("label", "ambiguous") for v in verdicts)
    persona_counts = Counter(v.get("declared_persona") or "(unknown)" for v in verdicts)

    attack_rate = (
        sum(label_counts.get(l, 0) for l in ATTACK_LABELS) / len(verdicts)
        if verdicts
        else 0.0
    )

    lines = ["## 요약", ""]
    lines.append(f"- **총 시나리오**: {total}")
    lines.append(f"- **judge 처리**: {len(verdicts)}")
    lines.append(f"- **공격 성공률**: {attack_rate:.1%} (partial_leak + attack_succeeded)")
    lines.append("")
    lines.append("### 라벨 분포")
    lines.append("")
    lines.append("| 라벨 | 건수 |")
    lines.append("|---|---:|")
    for label in LABEL_ORDER:
        lines.append(f"| {label} | {label_counts.get(label, 0)} |")
    lines.append("")
    lines.append("### 페르소나 분포")
    lines.append("")
    lines.append("| 페르소나 | 건수 |")
    lines.append("|---|---:|")
    for persona, count in persona_counts.most_common():
        lines.append(f"| {persona} | {count} |")
    lines.append("")
    return "\n".join(lines)


def _render_vector_matrix(verdicts: list[dict[str, Any]]) -> str:
    matrix: dict[str, Counter] = defaultdict(Counter)
    for v in verdicts:
        vector = v.get("judge_attack_vector") or v.get("declared_attack_vector") or "(unknown)"
        matrix[vector][v.get("label", "ambiguous")] += 1

    if not matrix:
        return "## 공격 벡터 × 라벨\n\n(데이터 없음)\n"

    lines = ["## 공격 벡터 × 라벨", ""]
    header = "| 벡터 | " + " | ".join(LABEL_ORDER) + " | 합계 |"
    sep = "|---|" + "---:|" * (len(LABEL_ORDER) + 1)
    lines.append(header)
    lines.append(sep)
    for vector in sorted(matrix.keys()):
        counts = matrix[vector]
        row = [vector]
        for label in LABEL_ORDER:
            row.append(str(counts.get(label, 0)))
        row.append(str(sum(counts.values())))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)


def _render_findings(
    verdicts: list[dict[str, Any]],
    fixture_by_name: dict[str, dict[str, Any]],
    promoted_names: set[str],
) -> str:
    findings = [v for v in verdicts if v.get("label") in ATTACK_LABELS]
    findings.sort(key=lambda v: (v.get("label"), -float(v.get("confidence", 0.0))))

    if not findings:
        return "## 신규 발견 취약점\n\n(없음 — 모두 안전 차단됨)\n"

    lines = ["## 신규 발견 취약점", ""]
    for v in findings:
        name = v.get("scenario_name", "?")
        scenario = fixture_by_name.get(name, {})
        attack_msg = scenario.get("message_text", "(메시지 없음)")
        promoted_mark = " 🆕 회귀 후보 편입됨" if name in promoted_names else ""
        confidence = float(v.get("confidence", 0.0))
        lines.append(f"### `{name}` — {v.get('label')} (conf={confidence:.2f}){promoted_mark}")
        lines.append("")
        vec = v.get("judge_attack_vector") or v.get("declared_attack_vector")
        if vec:
            lines.append(f"- **공격 벡터**: `{vec}`")
        lines.append(f"- **공격 메시지**: {attack_msg}")
        lines.append(f"- **판단 근거**: {v.get('rationale', '(없음)')}")
        lines.append("")
    return "\n".join(lines)


def _render_trend(history_dir: Path, current_summary: dict[str, int]) -> str:
    """최근 리포트들의 라벨 분포를 mermaid 라인 차트로 렌더."""
    if not history_dir.exists():
        return ""
    history_files = sorted(history_dir.glob("*.json"))
    if len(history_files) < 2:
        return ""

    series: dict[str, list[tuple[str, int]]] = {label: [] for label in LABEL_ORDER}
    for path in history_files[-10:]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = data.get("summary") or {}
        date_key = path.stem
        for label in LABEL_ORDER:
            series[label].append((date_key, int(summary.get(label, 0))))

    lines = ["## 트렌드 (최근 10회)", "", "```mermaid", "xychart-beta"]
    lines.append(f'title "공격 라벨 추이"')
    dates = [d for d, _ in series[LABEL_ORDER[0]]]
    if dates:
        lines.append(f'x-axis [{", ".join(dates)}]')
    lines.append('y-axis "건수"')
    for label in LABEL_ORDER:
        values = [str(v) for _, v in series[label]]
        if values and any(v != "0" for v in values):
            lines.append(f'line [{", ".join(values)}]')
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _save_summary_json(out_dir: Path, run_date: str, summary: dict[str, int], attack_rate: float) -> None:
    """트렌드 차트가 다음 회차에 읽을 수 있게 분포 메타만 별도 JSON으로 저장."""
    path = out_dir / f"{run_date}.json"
    payload = {"date": run_date, "summary": summary, "attack_rate": attack_rate}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render(
    *,
    report: dict[str, Any],
    verdicts_payload: dict[str, Any],
    fixture: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    out_dir: Path,
    run_date: str,
) -> Path:
    verdicts = verdicts_payload.get("verdicts", []) if isinstance(verdicts_payload, dict) else []
    fixture_by_name = {str(s.get("name")): s for s in fixture if isinstance(s, dict)}
    promoted_names = {str(c.get("name")) for c in candidates if isinstance(c, dict)}

    label_counts = Counter(v.get("label", "ambiguous") for v in verdicts)
    attack_rate = (
        sum(label_counts.get(l, 0) for l in ATTACK_LABELS) / len(verdicts)
        if verdicts else 0.0
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    sections = [
        f"# 적대적 평가 리포트 — {run_date}",
        "",
        f"- judge 모델: `{verdicts_payload.get('judge_model_id', '(unknown)')}`",
        f"- 입력 리포트: `total_cases={report.get('total_cases')}`, `passed_cases={report.get('passed_cases')}`",
        "",
        _render_summary(report, verdicts),
        _render_vector_matrix(verdicts),
        _render_findings(verdicts, fixture_by_name, promoted_names),
        _render_trend(out_dir, dict(label_counts)),
    ]
    content = "\n".join(s for s in sections if s)

    md_path = out_dir / f"{run_date}.md"
    md_path.write_text(content, encoding="utf-8")
    _save_summary_json(out_dir, run_date, dict(label_counts), attack_rate)

    # GitHub Actions step summary
    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        try:
            with open(gh_summary, "a", encoding="utf-8") as fp:
                fp.write(content)
                fp.write("\n")
        except OSError as exc:
            logger.warning("GITHUB_STEP_SUMMARY 기록 실패: %s", exc)

    return md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", required=True, help="run_agent_eval --json-out 결과")
    parser.add_argument("--verdicts", required=True, help="adversarial_judge --out 결과")
    parser.add_argument("--fixture", required=True, help="원본 시나리오 fixture")
    parser.add_argument(
        "--candidates",
        default=str(DEFAULT_CANDIDATES_PATH),
        help="회귀 후보 fixture (편입 여부 표시용)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"리포트 출력 디렉터리 (기본: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--date", default=date.today().isoformat(), help="리포트 날짜 (기본: 오늘)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    verdicts_payload = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))

    candidates_path = Path(args.candidates)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8")) if candidates_path.exists() else []

    md_path = render(
        report=report,
        verdicts_payload=verdicts_payload,
        fixture=fixture,
        candidates=candidates,
        out_dir=Path(args.out_dir),
        run_date=args.date,
    )
    logger.info("리포트 저장 → %s", md_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
