"""
Authentication & authorization helpers.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib only).
Tokens are signed HMAC-SHA256 tokens (JWT-like) with issued-at and expiry.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import UTC, datetime

import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db

SECRET_KEY = os.getenv("MIRAI_SECRET_KEY", secrets.token_hex(32))
TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 hours

ROLE_LEVELS = {
    "viewer": 0,
    "site": 1,
    "reviewer": 2,
    "admin": 3,
}

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256$120000${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(
    user_id: str,
    username: str,
    role: str,
    token_type: str = "access",
    ttl_seconds: int = TOKEN_TTL_SECONDS,
) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": user_id,
                "username": username,
                "role": role,
                "type": token_type,
                "iat": now,
                "exp": now + ttl_seconds,
            },
            ensure_ascii=False,
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = _b64url(
        hmac.new(SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256).digest()
    )
    return f"{signing_input}.{signature}"


def decode_token(token: str) -> dict | None:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(
            SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    from . import crud

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type", "access") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = crud.get_user(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")
    return user


def require_roles(*roles: str):
    """Return a dependency that requires one of the given roles."""

    def dependency(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency


def require_at_least(min_role: str):
    """Return a dependency requiring role level >= min_role."""
    min_level = ROLE_LEVELS.get(min_role, 0)

    def dependency(user=Depends(get_current_user)):
        if ROLE_LEVELS.get(user.role, 0) < min_level:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency


def utcnow():
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# TOTP (two-factor authentication)
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="MIRAI Carbon Navigator"
    )


def verify_totp(secret: str, code: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def create_2fa_temp_token(user) -> str:
    return create_token(
        user.user_id,
        user.username,
        user.role,
        token_type="2fa",
        ttl_seconds=5 * 60,
    )
