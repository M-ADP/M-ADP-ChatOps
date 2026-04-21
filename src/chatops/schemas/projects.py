from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "demo",
                "description": "데모 프로젝트",
            }
        }
    )


class ProjectResponse(BaseModel):
    project_id: int
    user_id: str
    name: str
    description: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1001,
                "user_id": "user-1",
                "name": "demo",
                "description": "데모 프로젝트",
                "status": "active",
                "created_at": "2026-04-20T10:00:00Z",
                "updated_at": "2026-04-20T10:00:00Z",
            }
        }
    )


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "projects": [
                    {
                        "project_id": 1001,
                        "user_id": "user-1",
                        "name": "demo",
                        "description": "데모 프로젝트",
                        "status": "active",
                        "created_at": "2026-04-20T10:00:00Z",
                        "updated_at": "2026-04-20T10:00:00Z",
                    }
                ]
            }
        }
    )
