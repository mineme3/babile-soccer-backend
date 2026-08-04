import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings

settings.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/babile_sport_test"
settings.redis_url = "redis://localhost:6379/1"
settings.secret_key = "test-secret"
settings.debug = False

from app.database import async_session_factory, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.base import Base  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_database():
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.database import engine as app_engine

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    await app_engine.dispose()


@pytest.fixture(autouse=True)
async def _close_redis():
    """Ensure the SSE redis client doesn't leak pending tasks after tests."""
    yield
    from app.services.sse import sse_service

    redis = sse_service._redis
    if redis is not None:
        sse_service._redis = None
        await redis.aclose()


@pytest.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def create_user():
    """Create a committed user and return (user, access_token)."""

    async def _make(role: str = "admin", email: str | None = None):
        from app.models.user import User, UserRole
        from app.services.auth import create_access_token, hash_password

        async with async_session_factory() as session:
            user = User(
                email=email or f"{role}-{uuid.uuid4().hex}@example.com",
                display_name=role,
                password_hash=hash_password("password123"),
                role=UserRole(role),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user, create_access_token(str(user.id), user.role.value)

    return _make


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db():
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
