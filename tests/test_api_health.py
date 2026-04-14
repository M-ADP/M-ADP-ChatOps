import json
import logging

from fastapi.testclient import TestClient

from chatops.app import create_app


def test_healthcheck_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/chatops/").status_code == 404


def test_swagger_ui_is_served_under_chatops_prefix() -> None:
    client = TestClient(create_app())

    prefixed = client.get("/chatops/docs")

    assert prefixed.status_code == 200
    assert client.get("/docs").status_code == 404


def _parse_audit_log(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(record.getMessage().split(" ", 1)[1])


def test_healthcheck_emits_http_and_action_audit_logs(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.http")
    caplog.set_level(logging.INFO, logger="chatops.actions")
    client = TestClient(create_app())

    response = client.get("/", headers={"X-User-Id": "user-1"})

    assert response.status_code == 200
    http_logs = [record for record in caplog.records if record.name == "chatops.http"]
    action_logs = [record for record in caplog.records if record.name == "chatops.actions"]
    assert http_logs
    assert action_logs
    http_payload = _parse_audit_log(http_logs[-1])
    action_payload = _parse_audit_log(action_logs[-1])
    assert http_payload["category"] == "http"
    assert http_payload["method"] == "GET"
    assert http_payload["path"] == "/"
    assert http_payload["status_code"] == 200
    assert http_payload["user_id"] == "user-1"
    assert action_payload["category"] == "action"
    assert action_payload["action"] == "healthcheck"
    assert action_payload["path"] == "/"
    assert action_payload["status_code"] == 200


def test_unmatched_route_emits_http_audit_log(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.http")
    client = TestClient(create_app())

    response = client.get("/missing")

    assert response.status_code == 404
    http_logs = [record for record in caplog.records if record.name == "chatops.http"]
    assert http_logs
    payload = _parse_audit_log(http_logs[-1])
    assert payload["category"] == "http"
    assert payload["path"] == "/missing"
    assert payload["status_code"] == 404
    assert "action" not in payload
