"""
Seed admin account into the database.

Run with: python -m app.seed_admin
(from the server directory with venv active)

Admin credentials are read from .env (ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_DISPLAY_NAME).
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine
from app.models.base import Base
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.services.auth import hash_password


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as db:
        repo = UserRepository(db)

        existing = await repo.get_by_email(settings.admin_email)
        if existing:
            print(f"  OK {settings.admin_email} already exists (role={existing.role.value})")
        else:
            await repo.create(
                email=settings.admin_email,
                display_name=settings.admin_display_name,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                is_verified=True,
                provider="local",
            )
            print(f"  CREATED admin: {settings.admin_email} (role=admin)")

        await db.commit()
    print("\nSeed complete!")


if __name__ == "__main__":
    print("Seeding Babile Sport admin...\n")
    asyncio.run(seed())
