from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatops.api.routers import build_api_router


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_api_router())
    return app
