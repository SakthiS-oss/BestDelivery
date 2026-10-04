"""ASGI entrypoint. Business logic stays in the feature modules."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.routes import router
from app.api.service import request_timeout_seconds

LOCAL_ORIGIN = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


class RequestTimeoutMiddleware:
    """Stop an HTTP request that runs longer than the configured budget."""

    def __init__(self, app: Callable[..., Awaitable[None]], timeout_seconds: float) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await asyncio.wait_for(self.app(scope, receive, send), self.timeout_seconds)
        except TimeoutError:
            response = JSONResponse(status_code=504, content={"detail": "request timed out"})
            await response(scope, receive, send)


def _operation_id(route: APIRoute) -> str:
    method = sorted(route.methods or {"GET"})[0].lower()
    path = route.path.strip("/").replace("/", "_").replace("{", "").replace("}", "") or "root"
    return f"{method}_{path}"


def create_app() -> FastAPI:
    """Mount the API and allow the local frontend to call it."""
    app = FastAPI(
        title="Chokepoint",
        description="Rank truck routes by drive time, hazards, and news.",
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=request_timeout_seconds())
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(router, prefix="/api")
    return app


app = create_app()
