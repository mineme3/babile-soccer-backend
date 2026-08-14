from contextlib import asynccontextmanager
import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.errors import register_error_handlers
from app.middleware import (
    DashboardOnlyMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import (
    admin,
    auth,
    competitions,
    health,
    matches,
    moderation,
    news,
    players,
    search,
    teams,
    upload,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.models.base import Base
    from app.models.user import User, UserRole
    from app.repositories.user import UserRepository
    from app.services.auth import hash_password
    from sqlalchemy.ext.asyncio import AsyncSession

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Auto-seed admin on first startup
    async with AsyncSession(engine) as db:
        repo = UserRepository(db)
        existing = await repo.get_by_email(settings.admin_email)
        if not existing:
            await repo.create(
                email=settings.admin_email,
                display_name=settings.admin_display_name,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                is_verified=True,
                provider="local",
            )
            await db.commit()
            print(f"[SEED] Admin created: {settings.admin_email}")

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Babile Sport API",
        description="Football live-score platform. Admin/staff insert all data; "
        "the mobile app consumes it in real time. Registration is optional.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dashboard-only middleware: admin endpoints are only accessible from the
    # Next.js dashboard, not from the mobile app.
    app.add_middleware(DashboardOnlyMiddleware)

    # Security headers on all responses
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting on auth endpoints
    app.add_middleware(RateLimitMiddleware)

    register_error_handlers(app)

    @app.get("/", include_in_schema=False)
    async def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/health", status_code=302)

    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(auth.router)
    app.include_router(matches.router)
    app.include_router(competitions.router)
    app.include_router(teams.router)
    app.include_router(players.router)
    app.include_router(news.router)
    app.include_router(search.router)
    app.include_router(moderation.router)
    app.include_router(upload.router)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.dev.ConsoleRenderer()
                if settings.debug
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return app


app = create_app()
