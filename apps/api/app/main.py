"""FastAPI application entry point and installation health endpoints."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import Database
from app.settings import Settings


class HealthResponse(BaseModel):
    """Stable process-health response."""

    service: str
    status: str
    version: str


class DependencyStatus(BaseModel):
    """Sanitized status for one external dependency."""

    status: str
    reason: str | None = None


class ReadinessResponse(BaseModel):
    """Stable readiness response used by supervisors and dashboards."""

    service: str
    status: str
    dependencies: dict[str, DependencyStatus]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API application with explicit settings for tests and workers."""

    resolved_settings = settings or Settings()
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.database = database
        yield
        database.close()

    application = FastAPI(
        title="Ebook Factory API",
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = resolved_settings

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        """Return process health without requiring external dependencies."""

        return HealthResponse(service=resolved_settings.service_name, status="ok", version=resolved_settings.version)

    @application.get("/ready", response_model=ReadinessResponse, tags=["operations"])
    def ready(request: Request) -> Any:
        """Return dependency readiness with sanitized database status."""

        result = request.app.state.database.check()
        payload = {
            "service": resolved_settings.service_name,
            "status": "ok" if result.status == "ok" else "not_ready",
            "dependencies": {"database": {"status": result.status}},
        }
        if result.reason:
            payload["dependencies"]["database"]["reason"] = result.reason
        status_code = 200 if result.status == "ok" else 503
        return JSONResponse(status_code=status_code, content=payload)

    return application


app = create_app()
