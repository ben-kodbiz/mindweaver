"""System endpoints: health, readiness, version."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from mindweaver import API_VERSION, APP_NAME, __version__
from mindweaver.database import session_scope

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readiness", summary="Readiness check", response_model=None)
def readiness(request: Request) -> JSONResponse | dict[str, object]:
    checks: dict[str, str] = {}
    try:
        with session_scope(request.app.state.session_factory) as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unreachable"

    if checks["database"] != "ok":
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


@router.get("/models", summary="Model gateway status")
def models(request: Request) -> list[dict[str, str | None]]:
    from mindweaver.gateway import provider_status

    return provider_status(request.app.state.settings)


@router.get("/version", summary="Application version")
def version() -> dict[str, str]:
    return {"name": APP_NAME, "version": __version__, "api_version": API_VERSION}
