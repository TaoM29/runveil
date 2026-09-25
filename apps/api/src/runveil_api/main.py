"""ASGI application entry point."""

from fastapi import FastAPI

from runveil_api.health import router


def create_app() -> FastAPI:
    app = FastAPI(title="Runveil API", version="0.1.0")
    app.include_router(router)
    return app


app = create_app()
