"""Structured error responses for the Babile Sport API.

Every error returned to clients follows a consistent shape:

    {
        "error": {
            "code": "MATCH_NOT_FOUND",
            "message": "The requested match could not be found.",
            "clue": "Check the match ID and try again."
        }
    }

This makes errors machine-parseable (``code``) and human-friendly (``message`` +
``clue``), which is exactly what a Flutter app or the dashboard needs to render
a useful UI.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# ── Error codes ────────────────────────────────────────────────

class ErrorCode:
    """Machine-readable error codes grouped by domain."""

    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Auth
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
    USERNAME_ALREADY_REGISTERED = "USERNAME_ALREADY_REGISTERED"
    PHONE_ALREADY_REGISTERED = "PHONE_ALREADY_REGISTERED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    REFRESH_TOKEN_REVOKED = "REFRESH_TOKEN_REVOKED"
    PASSWORD_TOO_WEAK = "PASSWORD_TOO_WEAK"
    PASSWORDS_DO_NOT_MATCH = "PASSWORDS_DO_NOT_MATCH"

    # Matches
    MATCH_NOT_FOUND = "MATCH_NOT_FOUND"
    MATCH_ALREADY_STARTED = "MATCH_ALREADY_STARTED"
    MATCH_INVALID_TRANSITION = "MATCH_INVALID_TRANSITION"
    DUPLICATE_FIXTURE = "DUPLICATE_FIXTURE"
    TEAM_NOT_IN_MATCH = "TEAM_NOT_IN_MATCH"
    PLAYER_NOT_IN_TEAM = "PLAYER_NOT_IN_TEAM"

    # Entities
    TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
    PLAYER_NOT_FOUND = "PLAYER_NOT_FOUND"
    COMPETITION_NOT_FOUND = "COMPETITION_NOT_FOUND"
    ARTICLE_NOT_FOUND = "ARTICLE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    FAVORITE_NOT_FOUND = "FAVORITE_NOT_FOUND"

    # Database
    DATABASE_CONSTRAINT = "DATABASE_CONSTRAINT"
    FOREIGN_KEY_VIOLATION = "FOREIGN_KEY_VIOLATION"
    UNIQUE_VIOLATION = "UNIQUE_VIOLATION"
    NOT_NULL_VIOLATION = "NOT_NULL_VIOLATION"

    # Upload
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    UPLOAD_FAILED = "UPLOAD_FAILED"


# ── Error response builder ──────────────────────────────────────

def error_response(
    code: str,
    message: str,
    clue: str = "",
    status_code: int = 400,
    details: Any = None,
) -> JSONResponse:
    """Build a structured error JSON response."""
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "clue": clue,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


# ── Map ValueError messages to structured errors ────────────────

_MATCH_ERROR_MAP: dict[str, tuple[str, str, str, int]] = {
    # message substring → (code, message, clue, status_code)
    "not found": (
        ErrorCode.MATCH_NOT_FOUND,
        "The requested match could not be found.",
        "Verify the match ID is correct and the match has not been deleted.",
        404,
    ),
    "duplicate fixture": (
        ErrorCode.DUPLICATE_FIXTURE,
        "A match between these two teams already exists at this time.",
        "Check the existing fixtures and choose a different kickoff time.",
        409,
    ),
    "team does not belong": (
        ErrorCode.TEAM_NOT_IN_MATCH,
        "The specified team is not part of this match.",
        "Ensure you are referencing a home or away team that belongs to this fixture.",
        400,
    ),
    "player does not belong": (
        ErrorCode.PLAYER_NOT_IN_TEAM,
        "The specified player is not registered to this team.",
        "Verify the player is assigned to the correct team before adding them to the lineup.",
        400,
    ),
}


def classify_match_error(exc: ValueError) -> JSONResponse:
    """Turn a MatchService ValueError into a structured error response."""
    msg = str(exc).lower()
    for substr, (code, message, clue, status) in _MATCH_ERROR_MAP.items():
        if substr in msg:
            return error_response(code, message, clue, status)
    # Fallback
    return error_response(
        ErrorCode.INTERNAL_ERROR,
        str(exc),
        "Please try again or contact support if the issue persists.",
        409,
    )


# ── Exception handlers registered in main.py ────────────────────

def register_error_handlers(app: FastAPI) -> None:
    """Attach all structured error handlers to the FastAPI app."""

    # ── 422 Validation Errors ───────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            fields.append({"field": loc, "message": err.get("msg", "Invalid value")})
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "The request contains invalid fields.",
            "Please check the highlighted fields and try again.",
            status_code=422,
            details=fields,
        )

    @app.exception_handler(ResponseValidationError)
    async def response_validation_handler(request: Request, exc: ResponseValidationError):
        logger.warning("Response validation error on %s %s: %s", request.method, request.url.path, exc)
        return error_response(
            ErrorCode.INTERNAL_ERROR,
            "An internal data format error occurred.",
            "This is a server issue. Please try again — if it persists, contact support.",
            status_code=500,
        )

    # ── Pydantic Validation ─────────────────────────────────
    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(request: Request, exc: PydanticValidationError):
        fields = []
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            fields.append({"field": loc, "message": err.get("msg", "Invalid value")})
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "The submitted data is invalid.",
            "Please correct the highlighted fields and resubmit.",
            status_code=422,
            details=fields,
        )

    # ── Database Integrity ──────────────────────────────────
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
        orig_str = str(exc.orig) if exc.orig else ""

        if "foreign key" in orig_str:
            return error_response(
                ErrorCode.FOREIGN_KEY_VIOLATION,
                "The request references a resource that does not exist.",
                "Check that all referenced IDs (team, player, competition) are valid and exist in the system.",
                status_code=409,
            )
        if "unique" in orig_str or "duplicate" in orig_str:
            # Try to extract the constraint name for a better clue
            detail = "A record with this information already exists."
            clue = "A unique field (email, username, phone, etc.) is already taken. Please use a different value."
            if "users_email_key" in orig_str:
                detail = "This email address is already registered."
                clue = "Try logging in instead, or use the password reset option if you forgot your password."
            elif "users_phone_key" in orig_str:
                detail = "This phone number is already registered."
                clue = "Try logging in with this phone number, or use a different number."
            elif "users_username_key" in orig_str:
                detail = "This username is already taken."
                clue = "Choose a different username — it must be unique across all users."
            return error_response(ErrorCode.UNIQUE_VIOLATION, detail, clue, status_code=409)
        if "not null" in orig_str:
            return error_response(
                ErrorCode.NOT_NULL_VIOLATION,
                "A required field is missing.",
                "Ensure all required fields are provided in the request.",
                status_code=400,
            )
        return error_response(
            ErrorCode.DATABASE_CONSTRAINT,
            "The request violates a database constraint.",
            "Please verify your input and try again.",
            status_code=409,
        )

    # ── Catch-all ───────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        from app.config import settings

        detail = str(exc) if settings.debug else "An unexpected error occurred."
        clue = (
            "This is an internal server error. "
            "Try refreshing or restarting the operation. "
            "If the problem continues, contact the support team."
        )
        return error_response(ErrorCode.INTERNAL_ERROR, detail, clue, status_code=500)
