from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class SlotModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ProjectCreateSlots(SlotModel):
    name: str | None = None
    max_cpu: float | int | None = None
    max_memory: float | int | None = None
    max_disk: float | int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _reject_blank_name(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("name")
    @classmethod
    def _require_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value:
            raise ValueError("name must not be blank")
        return value


class ProjectRenameSlots(SlotModel):
    project_name: str | None = None
    name: str | None = None


class MemberMutationSlots(SlotModel):
    project_name: str | None = None
    target_nickname: str | None = None


class ApplicationCreateSlots(SlotModel):
    project_name: str | None = None
    name: str | None = None
    cpu: float | int | None = None
    memory: float | int | None = None
    disk: float | int | None = None
    port: int | None = None


class ApplicationGithubSlots(SlotModel):
    project_name: str | None = None
    application_name: str | None = None
    owner: str | None = None
    repository: str | None = None
    branch: str | None = None


class MonitoringTrafficSlots(SlotModel):
    project_name: str | None = None
    application_name: str | None = None
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> "MonitoringTrafficSlots":
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be earlier than end")
        return self
