from fastapi import APIRouter

from chatops.api.routers.health import router as health_router


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(health_router)
    return router
