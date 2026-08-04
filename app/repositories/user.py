
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Favorite, RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_or_phone_or_username(self, identifier: str) -> User | None:
        """Login helper: try email, then phone, then username."""
        user = await self.get_by_email(identifier)
        if user:
            return user
        user = await self.get_by_phone(identifier)
        if user:
            return user
        return await self.get_by_username(identifier)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, RefreshToken)

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class FavoriteRepository(BaseRepository[Favorite]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Favorite)

    async def list_by_user(self, user_id) -> list[Favorite]:
        stmt = select(Favorite).where(Favorite.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
