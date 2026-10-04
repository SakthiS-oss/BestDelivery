"""ASGI entrypoint. Business logic stays in pipeline and the feature modules."""

from fastapi import FastAPI

from app.api.routes import router


def create_app() -> FastAPI:
    """Mount the API router."""
    app = FastAPI(title="Chokepoint")
    app.include_router(router, prefix="/api")
    return app


app = create_app()
