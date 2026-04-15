from chatops.services.follow_up_interpreter import FollowUpInterpreterService


def test_interpreter_maps_numeric_choice_to_previous_prompt_option() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="2",
        previous_request_status="ambiguous",
        session_context={
            "last_message_text": "앱 만들어줘",
            "last_effective_message_text": "앱 만들어줘",
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성", "label": "애플리케이션 생성"},
                    ],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.kind == "ambiguity_choice"
    assert rewritten.message_text == "앱 만들어줘\n애플리케이션 생성"


def test_interpreter_maps_letter_choice_to_previous_prompt_option() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="b",
        previous_request_status="ambiguous",
        session_context={
            "last_message_text": "작업해줘",
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성", "label": "애플리케이션 생성"},
                    ],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.message_text == "작업해줘\n애플리케이션 생성"


def test_interpreter_maps_partial_text_choice_to_previous_prompt_option() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="애플리케이션 생성",
        previous_request_status="ambiguous",
        session_context={
            "last_message_text": "생성해줘",
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "choice",
                    "options": [
                        {"value": "프로젝트 생성", "label": "프로젝트 생성"},
                        {"value": "애플리케이션 생성하기", "label": "애플리케이션 생성하기"},
                    ],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.message_text == "생성해줘\n애플리케이션 생성하기"


def test_interpreter_maps_single_missing_field_from_bare_value() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="killblack",
        previous_request_status="input_required",
        session_context={
            "last_missing_inputs": ["project_name"],
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [{"key": "project_name", "label": "대상 프로젝트"}],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.kind == "missing_input_fill"
    assert rewritten.message_text == "project_name=killblack"


def test_interpreter_extracts_value_from_labeled_single_missing_field() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="프로젝트 이름 : black",
        previous_request_status="input_required",
        session_context={
            "last_missing_inputs": ["name"],
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [{"key": "name", "label": "프로젝트 이름"}],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.kind == "missing_input_fill"
    assert rewritten.message_text == "name=black"


def test_interpreter_maps_comma_separated_values_by_missing_input_order() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="1, 1.2, 1, 8080",
        previous_request_status="input_required",
        session_context={
            "last_missing_inputs": ["cpu", "memory", "disk", "port"],
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [
                        {"key": "cpu", "label": "CPU"},
                        {"key": "memory", "label": "메모리"},
                        {"key": "disk", "label": "디스크"},
                        {"key": "port", "label": "포트"},
                    ],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.message_text == "cpu=1 memory=1.2 disk=1 port=8080"


def test_interpreter_extracts_values_from_labeled_comma_separated_missing_inputs() -> None:
    service = FollowUpInterpreterService()

    rewritten = service.rewrite(
        message_text="프로젝트 이름: black, 최대 CPU: 3",
        previous_request_status="input_required",
        session_context={
            "last_missing_inputs": ["name", "max_cpu"],
            "last_task_snapshot": {
                "follow_up_prompt": {
                    "kind": "missing_input",
                    "fields": [
                        {"key": "name", "label": "프로젝트 이름"},
                        {"key": "max_cpu", "label": "최대 CPU"},
                    ],
                }
            },
        },
    )

    assert rewritten is not None
    assert rewritten.message_text == "name=black max_cpu=3"
