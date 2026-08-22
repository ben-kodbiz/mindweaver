"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mindweaver import APP_NAME, __version__
from mindweaver.api.errors import register_exception_handlers
from mindweaver.api.middleware import RequestIDMiddleware
from mindweaver.api.routes.chat import router as chat_router
from mindweaver.api.routes.documents import router as documents_router
from mindweaver.api.routes.echo import router as echo_router
from mindweaver.api.routes.health import router as health_router
from mindweaver.api.routes.jobs import router as jobs_router
from mindweaver.api.routes.learning import router as learning_router
from mindweaver.api.routes.notebooks import router as notebooks_router
from mindweaver.api.routes.search import router as search_router
from mindweaver.config import Settings, get_settings
from mindweaver.database import build_engine, init_database, make_session_factory
from mindweaver.intelligence.routes import router as intelligence_router
from mindweaver.logging_conf import setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.app.log_level, secret=settings.security.secret_key)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_database(app.state.engine)
        yield

    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = build_engine(settings)
    app.state.session_factory = make_session_factory(app.state.engine)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router, prefix=settings.app.api_v1_prefix)
    app.include_router(echo_router, prefix=settings.app.api_v1_prefix)
    app.include_router(documents_router, prefix=f"{settings.app.api_v1_prefix}/documents")
    app.include_router(learning_router, prefix=f"{settings.app.api_v1_prefix}/documents")
    app.include_router(jobs_router, prefix=f"{settings.app.api_v1_prefix}/jobs")
    app.include_router(search_router, prefix=f"{settings.app.api_v1_prefix}/search")
    app.include_router(notebooks_router, prefix=f"{settings.app.api_v1_prefix}/notebooks")
    app.include_router(intelligence_router, prefix=f"{settings.app.api_v1_prefix}/intelligence")
    app.include_router(chat_router, prefix=f"{settings.app.api_v1_prefix}/chat")
    return app


app = create_app()
