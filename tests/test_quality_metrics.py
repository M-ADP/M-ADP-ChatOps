from __future__ import annotations

from types import SimpleNamespace

from chatops.evaluation.harness import ScenarioCase, ScenarioExpectation, ScenarioRunner


class StubGraphService:
    def handle_request(self, **kwargs):
        del kwargs
        return SimpleNamespace(
            status="completed",
            request_type="query",
            error_code=None,
            missing_inputs=None,
            selected_operation_ids=["project.list_projects"],
            resolved_references=None,
            final_response="조회 응답: ok",
            requires_approval=False,
            is_ambiguous=False,
        )


def test_quality_report_includes_production_audit_bands() -> None:
    runner = ScenarioRunner(
        graph_service=StubGraphService(),
        metadata_getter=lambda result: {
            "maintainability": 82,
            "extensibility": 79,
        },
    )

    report = runner.run(
        [
            ScenarioCase(
                name="query success",
                message_text="내 프로젝트 목록 보여줘",
                expectation=ScenarioExpectation(
                    status="completed",
                    request_type="query",
                    dispatched=False,
                ),
            )
        ]
    )

    assert report.metric_scores["maintainability"] == 82
    assert report.metric_scores["extensibility"] == 79
