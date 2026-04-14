from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from chatops.api.dependencies import get_auth_context, get_db_session
from chatops.api.routers.requests import _build_request_response
from chatops.common.logging.audit import AuditRoute
from chatops.db.repositories import RequestRepository
from chatops.schemas.auth import AuthContext
from chatops.schemas.requests import RequestListResponse


router = APIRouter(tags=["search"], route_class=AuditRoute)


@router.get("/requests/search", response_model=RequestListResponse)
def search_requests(
    query: str = Query(min_length=1),
    session_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    db_session: Session = Depends(get_db_session),
) -> RequestListResponse:
    items, total = RequestRepository(db_session).search_for_user(
        user_id=auth.user_id,
        query_text=query,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return RequestListResponse(
        items=[_build_request_response(record, record.message_text) for record in items],
        total=total,
        limit=limit,
        offset=offset,
    )
