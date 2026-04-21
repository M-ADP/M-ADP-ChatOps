from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session
from chatops.common.logging.audit import AuditRoute
from chatops.db.repositories import ProjectRepository
from chatops.schemas.auth import AuthContext
from chatops.schemas.projects import CreateProjectRequest, ProjectListResponse, ProjectResponse


router = APIRouter(prefix="/projects", tags=["projects"], route_class=AuditRoute)


def _build_project_response(record) -> ProjectResponse:
    return ProjectResponse(
        project_id=record.id,
        user_id=record.user_id,
        name=record.name,
        description=record.description,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> ProjectResponse:
    record = ProjectRepository(db_session).create(
        user_id=auth.user_id,
        name=payload.name,
        description=payload.description,
    )
    return _build_project_response(record)


@router.get("", response_model=ProjectListResponse)
def list_projects(
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> ProjectListResponse:
    records = ProjectRepository(db_session).list_for_user(user_id=auth.user_id)
    return ProjectListResponse(projects=[_build_project_response(r) for r in records])


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> ProjectResponse:
    record = ProjectRepository(db_session).get_for_user(project_id=project_id, user_id=auth.user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _build_project_response(record)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> None:
    deleted = ProjectRepository(db_session).delete_for_user(project_id=project_id, user_id=auth.user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
