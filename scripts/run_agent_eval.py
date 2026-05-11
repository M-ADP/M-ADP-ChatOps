"""Agent Loop 평가 실행 스크립트.

평가 대상:
  - false_completion_rate: 도구 호출 없이 완료를 주장하는 비율
  - tool_selection_accuracy: 기대한 operation_id 시퀀스와 일치하는 비율
  - tool_invocation_rate: 도구를 한 번이라도 호출해야 하는 시나리오에서 호출한 비율
  - avg_iterations: 시나리오당 평균 도구 호출 수

실제 Bedrock에 호출하지만 downstream API는 ScenarioDispatcher로 모킹한다.
checkpointer는 InMemorySaver를 사용해 DB 없이 동작하게 한다.

사용법:
    python scripts/run_agent_eval.py
    python scripts/run_agent_eval.py --fixture tests/evals/fixtures/agent_loop_eval_scenarios.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 프로젝트 루트 path 주입 (스크립트 단독 실행을 위해)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import boto3
from botocore.config import Config
from langgraph.checkpoint.memory import InMemorySaver

from chatops.common.config.settings import get_aws_config, get_bedrock_config
from chatops.evaluation.harness import (
    ScenarioRunner,
    load_quality_scenarios,
)
from chatops.evaluation.scenario_dispatcher import ScenarioDispatcher
from chatops.graph.service import GraphService
from chatops.services.llm import BedrockLLMService
from chatops.services.registry import RegistryService
from chatops.services.resolver import ParameterResolverService


DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "evals" / "fixtures" / "agent_loop_eval_scenarios.json"
REGISTRY_DIR = PROJECT_ROOT / "ai_registry"


def _build_bedrock_client():
    """앱과 동일하게 .env에서 credentials를 명시적으로 읽어 boto3에 주입한다."""
    aws_config = get_aws_config()
    bedrock_config = get_bedrock_config()
    return boto3.client(
        "bedrock-runtime",
        region_name=bedrock_config.region,
        aws_access_key_id=aws_config.aws_access_key_id,
        aws_secret_access_key=aws_config.aws_secret_access_key,
        config=Config(
            connect_timeout=20,
            read_timeout=60,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def _build_graph_service(dispatcher: ScenarioDispatcher) -> GraphService:
    bedrock_config = get_bedrock_config()
    bedrock_client = _build_bedrock_client()
    llm_service = BedrockLLMService(
        model_id=bedrock_config.model_id,
        timeout_seconds=60,
        client=bedrock_client,
    )
    registry_service = RegistryService.from_directory(
        REGISTRY_DIR,
        minimum_score_threshold=8,
        ambiguity_score_threshold=5,
    )
    return GraphService(
        llm_service=llm_service,
        registry_service=registry_service,
        downstream_dispatcher=dispatcher,
        resolver_service=ParameterResolverService(),
        checkpointer=InMemorySaver(),
    )


def _print_report(report) -> None:
    print()
    print("=" * 64)
    print(f"Total scenarios: {report.total_cases}")
    print(f"Passed:          {report.passed_cases}")
    print(f"Overall score:   {report.overall_score}")
    print("-" * 64)
    print("Agent metrics:")
    for key, value in report.agent_metrics.items():
        print(f"  {key:30s} {value}")
    print("-" * 64)
    print("Standard metrics:")
    for key, value in report.metric_scores.items():
        print(f"  {key:30s} {value}")
    print("-" * 64)
    print("Failures:")
    failures_seen = False
    for outcome in report.outcomes:
        if outcome.passed:
            continue
        failures_seen = True
        print(f"  [{outcome.name}]")
        for reason in outcome.failures:
            print(f"    - {reason}")
    if not failures_seen:
        print("  (none)")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Loop eval runner")
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help="시나리오 JSON 파일 경로",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="결과를 JSON 파일로 저장할 경로 (선택)",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="시나리오 이름에 포함된 문자열로 필터링 (예: --filter write_007)",
    )
    parser.add_argument(
        "--debug-bedrock",
        action="store_true",
        help="Bedrock에 전송되는 메시지/툴 스펙을 stderr에 출력",
    )
    args = parser.parse_args()

    if args.debug_bedrock:
        import logging
        logging.basicConfig(level=logging.INFO)
        # converse 호출 직전 인자 덤프
        import chatops.services.llm as _llm_mod
        _orig = _llm_mod.BedrockLLMService.converse_with_tools

        def _wrapped(self, messages, system_prompt, tool_specs, tool_choice=None):
            print("--- Bedrock converse_with_tools call ---", file=sys.stderr)
            print(f"model_id: {self.model_id}", file=sys.stderr)
            print(f"system_prompt (head): {system_prompt[:80]!r}...", file=sys.stderr)
            print(f"tool_choice: {tool_choice}", file=sys.stderr)
            print(f"messages ({len(messages)}):", file=sys.stderr)
            for i, msg in enumerate(messages):
                print(f"  [{i}] role={msg.get('role')!r}", file=sys.stderr)
                content = msg.get("content", [])
                for j, block in enumerate(content):
                    if isinstance(block, dict):
                        keys = list(block.keys())
                        if "text" in block:
                            text = block["text"]
                            print(f"      content[{j}] text={text!r} (len={len(text) if isinstance(text, str) else 'NA'})", file=sys.stderr)
                        else:
                            print(f"      content[{j}] keys={keys}", file=sys.stderr)
                    else:
                        print(f"      content[{j}] type={type(block).__name__}", file=sys.stderr)
            print(f"tool_specs count: {len(tool_specs)}", file=sys.stderr)
            print("---", file=sys.stderr)
            return _orig(self, messages, system_prompt, tool_specs, tool_choice)

        _llm_mod.BedrockLLMService.converse_with_tools = _wrapped

        # preview_request 결과도 디버그
        import chatops.graph.service as _svc_mod
        _orig_preview = _svc_mod.GraphService.preview_request

        def _wrapped_preview(self, message_text, session_context=None):
            result = _orig_preview(self, message_text, session_context)
            print(f"--- preview_request -> {result}", file=sys.stderr)
            return result

        _svc_mod.GraphService.preview_request = _wrapped_preview

        # _tool_choice_for_state 결과도 덤프
        import chatops.graph.agent_loop as _agent_mod
        _orig_tc = _agent_mod._tool_choice_for_state

        def _wrapped_tc(state):
            tc = _orig_tc(state)
            print(
                f"--- _tool_choice_for_state: request_type={state.get('request_type')!r}, "
                f"intent={state.get('intent')!r}, executed_ops={len(state.get('executed_operations', []) or [])}, "
                f"-> {tc}",
                file=sys.stderr,
            )
            return tc

        _agent_mod._tool_choice_for_state = _wrapped_tc

    fixture_path = Path(args.fixture).resolve()
    if not fixture_path.exists():
        print(f"fixture not found: {fixture_path}", file=sys.stderr)
        return 2

    scenarios = load_quality_scenarios(fixture_path)
    print(f"Loaded {len(scenarios)} scenarios from {fixture_path}")

    if args.filter:
        scenarios = [s for s in scenarios if args.filter in s.name]
        print(f"Filtered to {len(scenarios)} scenarios matching {args.filter!r}")

    dispatcher = ScenarioDispatcher()
    graph_service = _build_graph_service(dispatcher)

    runner = ScenarioRunner(
        graph_service=graph_service,
        dispatch_count_getter=lambda: len(dispatcher.executed_operation_ids),
        scenario_dispatcher=dispatcher,
    )

    report = runner.run(scenarios)
    _print_report(report)

    if args.json_out:
        out_path = Path(args.json_out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fp:
            json.dump(
                {
                    "total_cases": report.total_cases,
                    "passed_cases": report.passed_cases,
                    "overall_score": report.overall_score,
                    "agent_metrics": report.agent_metrics,
                    "metric_scores": report.metric_scores,
                    "outcomes": [
                        {
                            "name": o.name,
                            "passed": o.passed,
                            "failures": list(o.failures),
                            "executed_operation_ids": list(o.executed_operation_ids),
                            "final_response": getattr(o.result, "final_response", None) or "",
                            "status": getattr(o.result, "status", None),
                            "request_type": getattr(o.result, "request_type", None),
                            "requires_approval": bool(getattr(o.result, "requires_approval", False)),
                            "is_ambiguous": bool(getattr(o.result, "is_ambiguous", False)),
                        }
                        for o in report.outcomes
                    ],
                },
                fp,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Report saved to {out_path}")

    return 0 if report.passed_cases == report.total_cases else 1


if __name__ == "__main__":
    sys.exit(main())
