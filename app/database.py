import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Neon requires SSL — asyncpg uses this via connect_args
_connect_args: dict = {}
if "neon.tech" in settings.database_url or settings.environment == "production":
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _connect_args["ssl"] = ctx

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5 if settings.environment == "production" else 10,
    max_overflow=5 if settings.environment == "production" else 20,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=_connect_args,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
