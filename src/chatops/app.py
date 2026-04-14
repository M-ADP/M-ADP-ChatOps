from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatops.api.routers import build_api_router
from chatops.api.routers.health import router as health_router
from chatops.common.logging.audit import AuditLogMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        docs_url="/chatops/docs",
        openapi_url="/chatops/openapi.json",
    )
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(build_api_router())
    return app
