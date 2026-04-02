from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    step_id: str
    title: str
    status: str
    operation_id: str | None = None


class PlanObject(BaseModel):
    goal: str
    specialist: str
    entities: dict[str, object] = Field(default_factory=dict)
    constraints: dict[str, object] = Field(default_factory=dict)
    candidate_steps: list[PlanStep] = Field(default_factory=list)
    risk_level: str | None = None
    required_clarifications: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "goal": "demo 프로젝트에 api 앱 생성",
                "specialist": "application",
                "entities": {"project_name": "demo", "application_name": "api"},
                "constraints": {"approval_required": True},
                "candidate_steps": [
                    {
                        "step_id": "create-app",
                        "title": "앱 생성",
                        "status": "planned",
                        "operation_id": "application.create_apps",
                    }
                ],
                "risk_level": "medium",
                "required_clarifications": ["cpu", "memory", "disk"],
            }
        }
    )


class SpecialistResult(BaseModel):
    specialist: str
    operation_id: str | None = None
    summary: str | None = None
    resolved_inputs: dict[str, object] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)


class VerifierDecision(BaseModel):
    decision: str
    summary: str
    missing_inputs: list[str] = Field(default_factory=list)
    follow_up_action: str | None = None


class SessionSummary(BaseModel):
    active_goal: str | None = None
    recent_entities: dict[str, object] = Field(default_factory=dict)
    last_completed_task: str | None = None
    last_verifier_decision: str | None = None
    updated_at: datetime
