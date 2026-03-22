from __future__ import annotations


class FakeMonitoringClientImpl:
    async def get_app_deployment_traffic(
        self,
        *,
        user_id: str,
        role: str | None,
        project_id: int,
        app_deployment_name: str,
    ) -> dict[str, object]:
        del user_id, role
        return {
            "summary": "현재 앱 트래픽 상태는 downstream 연동 전입니다.",
            "project_id": project_id,
            "app_deployment_name": app_deployment_name,
        }
