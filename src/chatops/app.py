import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from chatops.api.routers import build_api_router
from chatops.api.routers.health import router as health_router
from chatops.common.logging.audit import AuditLogMiddleware

logger = logging.getLogger(__name__)

_SHUTDOWN_THREAD_JOIN_TIMEOUT = 30.0
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _run_migrations() -> None:
    """서버 시작 시 alembic upgrade head를 실행한다."""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))

        from chatops.common.config.settings import get_db_config
        alembic_cfg.set_main_option("sqlalchemy.url", get_db_config().url)

        command.upgrade(alembic_cfg, "head")
        logger.info("alembic upgrade head completed")
    except Exception:
        logger.exception("alembic migration failed — server will still start")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
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
