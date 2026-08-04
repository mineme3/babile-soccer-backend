from datetime import UTC, datetime, timedelta
import uuid as uuid_lib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.errors import error_response, ErrorCode
from app.models.user import User, UserRole
from app.repositories.user import FavoriteRepository, RefreshTokenRepository, UserRepository
from app.schemas.user import (
    AdminUserCreate,
    AdminUserUpdate,
    FavoriteCreate,
    FavoriteResponse,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    ResetPasswordRequest,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    require_admin,
    verify_password,
)
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

# In-memory store for password reset tokens (production: use Redis)
_password_reset_tokens: dict[str, tuple[str, datetime]] = {}


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)

    # Check email uniqueness
    if body.email:
        existing = await repo.get_by_email(body.email)
        if existing:
            return error_response(
                ErrorCode.EMAIL_ALREADY_REGISTERED,
                "This email address is already registered.",
                "Try logging in instead, or use the password reset option if you forgot your password.",
                status_code=409,
            )

    # Check phone uniqueness
    if body.phone:
        existing = await repo.get_by_phone(body.phone)
        if existing:
            return error_response(
                ErrorCode.PHONE_ALREADY_REGISTERED,
                "This phone number is already registered.",
                "Try logging in with this phone number, or use a different number.",
                status_code=409,
            )

    # Check username uniqueness
    if body.username:
        existing = await repo.get_by_username(body.username)
        if existing:
            return error_response(
                ErrorCode.USERNAME_ALREADY_REGISTERED,
                "This username is already taken.",
                "Choose a different username — it must be unique across all users.",
                status_code=409,
            )

    # Require at least one contact method
    if not body.email and not body.phone:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "At least an email or phone number is required.",
            "Provide an email address or phone number so we can verify your account.",
            status_code=422,
        )

    user = await repo.create(
        email=body.email,
        phone=body.phone,
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=UserRole.USER,
        provider="local",
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = None

    # Try login by email, phone, or username
    if body.email:
        user = await repo.get_by_email(body.email)
    elif body.phone:
        user = await repo.get_by_phone(body.phone)
    elif body.username:
        user = await repo.get_by_username(body.username)

    if not user or not verify_password(body.password, user.password_hash):
        return error_response(
            ErrorCode.INVALID_CREDENTIALS,
            "Invalid login credentials.",
            "Check your email/username and password. If you forgot your password, use the 'Forgot Password' option.",
            status_code=401,
        )

    if not user.is_active:
        return error_response(
            ErrorCode.FORBIDDEN,
            "Your account has been deactivated.",
            "Contact the support team to reactivate your account.",
            status_code=403,
        )

    # Dashboard login is NOT allowed through this endpoint — must use /admin/login
    is_dashboard = request.headers.get("X-Dashboard-Client") == "babile-dashboard"
    if is_dashboard:
        return error_response(
            ErrorCode.FORBIDDEN,
            "Dashboard login is not available through this endpoint.",
            "Use the admin login portal at /admin/login.",
            status_code=403,
        )

    access = create_access_token(str(user.id), user.role.value)
    refresh = create_refresh_token(str(user.id), user.role.value)
    refresh_repo = RefreshTokenRepository(db)
    await refresh_repo.create(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(body: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """Dedicated admin-only login endpoint for the dashboard.

    Only accessible when the X-Dashboard-Client header is present,
    and only grants access to users with ADMIN role.
    """
    # Must come from the dashboard
    is_dashboard = request.headers.get("X-Dashboard-Client") == "babile-dashboard"
    if not is_dashboard:
        return error_response(
            ErrorCode.FORBIDDEN,
            "This endpoint is only accessible from the admin dashboard.",
            "Access the admin portal at the dashboard login page.",
            status_code=403,
        )

    # Must provide email
    if not body.email:
        return error_response(
            ErrorCode.INVALID_CREDENTIALS,
            "Admin login requires an email address.",
            "Enter the admin email address to sign in.",
            status_code=401,
        )

    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)

    if not user or not verify_password(body.password, user.password_hash):
        return error_response(
            ErrorCode.INVALID_CREDENTIALS,
            "Invalid admin credentials.",
            "Check your email and password. Only admin accounts can access the dashboard.",
            status_code=401,
        )

    if not user.is_active:
        return error_response(
            ErrorCode.FORBIDDEN,
            "Your admin account has been deactivated.",
            "Contact the system administrator to reactivate your account.",
            status_code=403,
        )

    # STRICT: Only ADMIN role can login through this endpoint
    if user.role != UserRole.ADMIN:
        return error_response(
            ErrorCode.FORBIDDEN,
            "Access denied. Admin privileges required.",
            "Only accounts created through the admin seed can access the dashboard.",
            status_code=403,
        )

    access = create_access_token(str(user.id), user.role.value)
    refresh = create_refresh_token(str(user.id), user.role.value)
    refresh_repo = RefreshTokenRepository(db)
    await refresh_repo.create(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: TokenRefresh, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        return error_response(
            ErrorCode.TOKEN_INVALID,
            "Invalid token type.",
            "Please log in again to get a new token.",
            status_code=401,
        )
    refresh_repo = RefreshTokenRepository(db)
    stored = await refresh_repo.get_by_token_hash(hash_token(body.refresh_token))
    if not stored:
        return error_response(
            ErrorCode.REFRESH_TOKEN_REVOKED,
            "This refresh token has been revoked or expired.",
            "Please log in again to get a new token.",
            status_code=401,
        )
    stored.is_revoked = True
    await db.flush()
    user_id = payload["sub"]
    role = payload.get("role", "user")
    access = create_access_token(user_id, role)
    new_refresh = create_refresh_token(user_id, role)
    await refresh_repo.create(
        user_id=stored.user_id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)

    # Check username uniqueness if updating
    if body.username and body.username != current_user.username:
        existing = await repo.get_by_username(body.username)
        if existing:
            return error_response(
                ErrorCode.USERNAME_ALREADY_REGISTERED,
                "This username is already taken.",
                "Choose a different username — it must be unique across all users.",
                status_code=409,
            )

    update_data = body.model_dump(exclude_none=True)
    updated = await repo.update(current_user.id, **update_data)
    return updated


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Send a password reset token via email."""
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)

    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If an account exists with that email, a reset link has been sent."}

    # Generate a secure reset token
    reset_token = secrets.token_urlsafe(32)
    _password_reset_tokens[reset_token] = (
        str(user.id),
        datetime.now(UTC) + timedelta(hours=1),
    )

    # Send the reset email
    send_password_reset_email(body.email, reset_token)

    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using a valid token."""
    token_data = _password_reset_tokens.get(body.token)
    if not token_data:
        return error_response(
            ErrorCode.TOKEN_INVALID,
            "Invalid or expired reset token.",
            "Request a new password reset link.",
            status_code=400,
        )

    user_id, expires_at = token_data
    if datetime.now(UTC) > expires_at:
        del _password_reset_tokens[body.token]
        return error_response(
            ErrorCode.TOKEN_EXPIRED,
            "Reset token has expired.",
            "Request a new password reset link.",
            status_code=400,
        )

    repo = UserRepository(db)
    user = await repo.get(uuid_lib.UUID(user_id))
    if not user:
        return error_response(
            ErrorCode.USER_NOT_FOUND,
            "User account not found.",
            "The account may have been deleted. Contact support.",
            status_code=404,
        )

    await repo.update(user.id, password_hash=hash_password(body.new_password))
    del _password_reset_tokens[body.token]

    return {"message": "Password has been reset successfully. You can now log in with your new password."}


@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    """Login or register via Google OAuth id_token.

    In production, verify the id_token with Google's tokeninfo endpoint.
    For now, accept the token and extract user info (development mode).
    """
    try:
        # TODO: Verify with Google in production
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={body.id_token}")
        #     if resp.status_code != 200:
        #         raise ValueError("Invalid Google token")
        #     google_user = resp.json()

        # Development placeholder — decode JWT payload without verification
        import base64
        parts = body.id_token.split(".")
        if len(parts) != 3:
            return error_response(
                ErrorCode.TOKEN_INVALID,
                "Invalid Google token format.",
                "Please try signing in again.",
                status_code=401,
            )
        payload_bytes = parts[1] + "=" * (4 - len(parts[1]) % 4)
        google_user = __import__("json").loads(base64.urlsafe_b64decode(payload_bytes))

        google_email = google_user.get("email")
        google_name = google_user.get("name", "")
        google_picture = google_user.get("picture")

        if not google_email:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Could not extract email from Google token.",
                "Try signing in again or use email/password login.",
                status_code=401,
            )
    except Exception:
        return error_response(
            ErrorCode.TOKEN_INVALID,
            "Failed to verify Google token.",
            "Please try signing in again, or use email/password login.",
            status_code=401,
        )

    repo = UserRepository(db)
    user = await repo.get_by_email(google_email)

    if user:
        # Existing user — log them in
        if not user.is_active:
            return error_response(
                ErrorCode.FORBIDDEN,
                "Your account has been deactivated.",
                "Contact the support team to reactivate your account.",
                status_code=403,
            )
        # Update avatar if changed
        if google_picture and user.avatar_url != google_picture:
            await repo.update(user.id, avatar_url=google_picture)
    else:
        # Create new user from Google info
        username = google_email.split("@")[0]
        # Ensure username is unique
        existing_username = await repo.get_by_username(username)
        if existing_username:
            username = f"{username}_{secrets.token_hex(3)}"

        user = await repo.create(
            email=google_email,
            username=username,
            display_name=google_name or username,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=UserRole.USER,
            is_verified=True,
            avatar_url=google_picture,
            provider="google",
        )

    access = create_access_token(str(user.id), user.role.value)
    refresh = create_refresh_token(str(user.id), user.role.value)
    refresh_repo = RefreshTokenRepository(db)
    await refresh_repo.create(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Favorites ────────────────────────────────────────────────

@router.get("/favorites", response_model=list[FavoriteResponse])
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepository(db)
    return await repo.list_by_user(current_user.id)


@router.post("/favorites", response_model=FavoriteResponse, status_code=201)
async def add_favorite(
    body: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepository(db)
    return await repo.create(
        user_id=current_user.id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )


@router.delete("/favorites/{favorite_id}", status_code=204)
async def remove_favorite(
    favorite_id: uuid_lib.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepository(db)
    # Verify ownership before deletion (prevents IDOR)
    from sqlalchemy import select
    from app.models.user import Favorite
    stmt = select(Favorite).where(
        Favorite.id == favorite_id,
        Favorite.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    favorite = result.scalar_one_or_none()
    if not favorite:
        return error_response(
            ErrorCode.FAVORITE_NOT_FOUND,
            "Favorite not found.",
            "This favorite may have already been removed or does not belong to you.",
            status_code=404,
        )
    await db.delete(favorite)
    await db.flush()


# ── Admin endpoints (dashboard only) ──────────────────────────

@router.get("/admin/users", response_model=list[UserResponse])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    return await repo.list(limit=100)


@router.post("/admin/users", response_model=UserResponse, status_code=201)
async def create_staff(
    body: AdminUserCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    if body.email:
        existing = await repo.get_by_email(body.email)
        if existing:
            return error_response(
                ErrorCode.EMAIL_ALREADY_REGISTERED,
                "This email address is already registered.",
                "Use a different email address.",
                status_code=409,
            )
    if body.phone:
        existing = await repo.get_by_phone(body.phone)
        if existing:
            return error_response(
                ErrorCode.PHONE_ALREADY_REGISTERED,
                "This phone number is already registered.",
                "Use a different phone number.",
                status_code=409,
            )
    if body.username:
        existing = await repo.get_by_username(body.username)
        if existing:
            return error_response(
                ErrorCode.USERNAME_ALREADY_REGISTERED,
                "This username is already taken.",
                "Choose a different username.",
                status_code=409,
            )
    user = await repo.create(
        email=body.email,
        phone=body.phone,
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
        provider="local",
    )
    return user


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid_lib.UUID,
    body: AdminUserUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.update(user_id, **body.model_dump(exclude_none=True))
    if not user:
        return error_response(
            ErrorCode.USER_NOT_FOUND,
            "User not found.",
            "Check the user ID and try again.",
            status_code=404,
        )
    return user
