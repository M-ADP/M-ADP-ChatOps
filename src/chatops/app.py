from contextlib import asynccontextmanager

from fastapi import FastAPI

from chatops.api.routers import build_api_router
from chatops.api.routers.health import router as health_router
from chatops.common.logging.audit import AuditLogMiddleware

_SHUTDOWN_THREAD_JOIN_TIMEOUT = 30.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Graceful shutdown: 진행 중인 background 요청 스레드를 최대 30초 대기
    from chatops.api.routers.requests import _active_threads, _active_threads_lock
    with _active_threads_lock:
        threads = list(_active_threads)
    for t in threads:
        t.join(timeout=_SHUTDOWN_THREAD_JOIN_TIMEOUT)


def create_app() -> FastAPI:
    app = FastAPI(
        docs_url="/chatops/docs",
        openapi_url="/chatops/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(AuditLogMiddleware)
    app.include_router(health_router)
    app.include_router(build_api_router())
    return app
