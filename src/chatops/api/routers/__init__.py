from fastapi import APIRouter

from chatops.api.routers.health import router as health_router
from chatops.api.routers.requests import router as request_router
from chatops.api.routers.sessions import router as session_router


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(health_router)
    router.include_router(session_router)
    router.include_router(request_router)
    return router
