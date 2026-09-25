"""ASGI application entry point."""

from fastapi import FastAPI

from agentrail_api.health import router


def create_app() -> FastAPI:
    app = FastAPI(title="AgentRail API", version="0.1.0")
    app.include_router(router)
    return app


app = create_app()
