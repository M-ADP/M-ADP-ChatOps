from __future__ import annotations

import importlib

from chatops.infra.client.fake_application_impl import FakeApplicationClientImpl
from chatops.infra.client.fake_monitoring_impl import FakeMonitoringClientImpl
from chatops.infra.client.fake_project_impl import FakeProjectClientImpl


def test_get_project_client_returns_fake_when_toggle_enabled(monkeypatch) -> None:
    monkeypatch.setenv("USE_FAKE_PROJECT_CLIENT", "true")

    project_module = importlib.import_module("chatops.dependencies.client.project")
    project_module._get_fake_config.cache_clear()

    client = project_module.get_project_client()

    assert isinstance(client, FakeProjectClientImpl)


def test_get_application_client_returns_fake_when_toggle_enabled(monkeypatch) -> None:
    monkeypatch.setenv("USE_FAKE_APPLICATION_CLIENT", "true")

    application_module = importlib.import_module("chatops.dependencies.client.application")
    application_module._get_fake_config.cache_clear()

    client = application_module.get_application_client()

    assert isinstance(client, FakeApplicationClientImpl)


def test_get_monitoring_client_returns_fake_when_toggle_enabled(monkeypatch) -> None:
    monkeypatch.setenv("USE_FAKE_MONITORING_CLIENT", "true")

    monitoring_module = importlib.import_module("chatops.dependencies.client.monitoring")
    monitoring_module._get_fake_config.cache_clear()

    client = monitoring_module.get_monitoring_client()

    assert isinstance(client, FakeMonitoringClientImpl)


def test_get_project_client_returns_real_impl_when_toggle_disabled(monkeypatch) -> None:
    monkeypatch.setenv("USE_FAKE_PROJECT_CLIENT", "false")

    project_module = importlib.import_module("chatops.dependencies.client.project")
    project_module._get_fake_config.cache_clear()

    client = project_module.get_project_client()

    assert client.__class__.__name__ == "ProjectClientImpl"
