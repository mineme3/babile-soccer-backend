from typing import Literal
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (asyncpg driver)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/babile_sport"

    # Redis (used for real-time SSE pub/sub)
    redis_url: str = "redis://localhost:6379/0"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    # Admin seed credentials
    admin_email: str = "admin@babile.com"
    admin_password: str = "Admin@123"
    admin_display_name: str = "Admin Operator"

    # App
    port: int = 8000
    debug: bool = True
    cors_origins: str = "*"
    environment: Literal["development", "staging", "production"] = "development"
    frontend_url: str = "http://localhost:3000"

    # ImageKit
    imagekit_url_endpoint: str = ""
    imagekit_public_key: str = ""
    imagekit_private_key: str = ""

    # Email (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "Babile Sport <noreply@babilesport.com>"

    def model_post_init(self, __context) -> None:
        """Post-init processing: auto-convert URLs for drivers."""
        # Neon provides postgresql:// but asyncpg needs postgresql+asyncpg://
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        # asyncpg doesn't understand libpq query params (sslmode, channel_binding, etc.)
        # Strip them and set SSL via connect_args instead
        parsed = urlparse(self.database_url)
        if parsed.query:
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            self.database_url = clean

        # Upstash: build redis_url from REST credentials if not explicitly set
        if self.upstash_redis_rest_url and not self.redis_url.startswith("rediss://"):
            parsed = urlparse(self.upstash_redis_rest_url)
            host = parsed.hostname or ""
            token = self.upstash_redis_rest_token
            self.redis_url = f"rediss://:{token}@{host}:6379"


settings = Settings()
