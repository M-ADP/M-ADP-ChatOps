from fastapi import APIRouter

from chatops.common.logging.audit import AuditRoute

router = APIRouter(route_class=AuditRoute)


@router.get("/")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
