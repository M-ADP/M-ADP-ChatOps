from fastapi import FastAPI

from chatops.api.routers import build_api_router


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(build_api_router())
    return app
