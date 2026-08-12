import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import (
    create_2fa_temp_token,
    create_token,
    decode_token,
    generate_totp_secret,
    get_current_user,
    totp_uri,
    verify_password,
    verify_totp,
)
from ..services import oidc

router = APIRouter(prefix="/api/auth", tags=["auth"])

_oidc_states: dict[str, float] = {}
_oidc_codes: dict[str, dict] = {}
_login_failures: dict[str, list[float]] = {}

_LOGIN_FAILURE_WINDOW = 15 * 60
_LOGIN_LOCKOUT_SECONDS = 15 * 60
_MAX_LOGIN_FAILURES = int(os.getenv("MIRAI_LOGIN_MAX_FAILURES", "10"))


def _login_key(username: str, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{username.lower()}|{ip}"


def _check_login_throttle(key: str) -> None:
    now = time.time()
    failures = [t for t in _login_failures.get(key, []) if now - t < _LOGIN_FAILURE_WINDOW]
    if len(failures) >= _MAX_LOGIN_FAILURES:
        oldest = min(failures) if failures else now
        retry_after = max(1, int(_LOGIN_LOCKOUT_SECONDS - (now - oldest)))
        raise HTTPException(
            status_code=429,
            detail="ログイン試行回数が上限を超えました。しばらく待ってから再試行してください。",
            headers={"Retry-After": str(retry_after)},
        )
    _login_failures[key] = failures


def _record_login_failure(key: str) -> None:
    now = time.time()
    failures = [t for t in _login_failures.get(key, []) if now - t < _LOGIN_FAILURE_WINDOW]
    failures.append(now)
    _login_failures[key] = failures


@router.post("/login", response_model=schemas.LoginResponse)
def login(
    body: schemas.LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    key = _login_key(body.username, request)
    _check_login_throttle(key)
    user = crud.get_user_by_username(db, body.username)
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        _record_login_failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _login_failures.pop(key, None)
    if user.is_2fa_enabled:
        crud.add_audit_log(db, user.username, "login", "user", user.user_id, "2fa pending")
        return schemas.LoginResponse(
            access_token="",
            requires_2fa=True,
            temp_token=create_2fa_temp_token(user),
            user=user,
        )
    token = create_token(user.user_id, user.username, user.role)
    crud.add_audit_log(db, user.username, "login", "user", user.user_id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/2fa/login", response_model=schemas.TokenResponse)
def twofa_login(body: schemas.TotpLoginRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.temp_token)
    if not payload or payload.get("type") != "2fa":
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA session")
    user = crud.get_user(db, payload["sub"])
    if not user or not user.is_active or not user.totp_secret:
        raise HTTPException(status_code=401, detail="2FA not configured")
    if not verify_totp(user.totp_secret, body.code.strip()):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")
    token = create_token(user.user_id, user.username, user.role)
    crud.add_audit_log(db, user.username, "login", "user", user.user_id, "2fa verified")
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/2fa/setup", response_model=schemas.TotpSetupResponse)
def twofa_setup(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.totp_secret and user.is_2fa_enabled:
        return schemas.TotpSetupResponse(
            secret=user.totp_secret,
            otpauth_url=totp_uri(user.totp_secret, user.username),
            already_enabled=True,
        )
    secret = user.totp_secret or generate_totp_secret()
    if not user.totp_secret:
        user.totp_secret = secret
        db.commit()
        db.refresh(user)
    return schemas.TotpSetupResponse(
        secret=secret,
        otpauth_url=totp_uri(secret, user.username),
        already_enabled=False,
    )


@router.post("/2fa/verify", response_model=schemas.UserRead)
def twofa_verify(
    body: schemas.TotpVerifyRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    if not verify_totp(user.totp_secret, body.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
    return crud.set_user_totp(db, user.user_id, user.totp_secret)


@router.post("/2fa/disable", response_model=schemas.UserRead)
def twofa_disable(
    body: schemas.TotpVerifyRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    if not verify_totp(user.totp_secret, body.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
    user.totp_secret = None
    user.is_2fa_enabled = False
    db.commit()
    db.refresh(user)
    crud.add_audit_log(db, user.username, "update", "user", user.user_id, "2fa disabled")
    return user


@router.get("/me", response_model=schemas.UserRead)
def me(user=Depends(get_current_user)):
    return user


@router.get("/oidc/login")
def oidc_login():
    if not oidc.oidc_enabled():
        raise HTTPException(status_code=400, detail="OIDC is not configured")
    state = secrets.token_hex(16)
    _oidc_states[state] = time.time() + 600
    return RedirectResponse(oidc.authorization_url(state))


@router.get("/oidc/status")
def oidc_status():
    enabled = oidc.oidc_enabled()
    provider = None
    if enabled:
        issuer = __import__("os").getenv("MIRAI_OIDC_ISSUER", "")
        provider = issuer.rstrip("/").split("//")[-1] if issuer else None
    return {"enabled": enabled, "provider": provider}


@router.get("/oidc/callback")
def oidc_callback(code: str, state: str, db: Session = Depends(get_db)):
    if not oidc.oidc_enabled():
        raise HTTPException(status_code=400, detail="OIDC is not configured")
    if _oidc_states.pop(state, 0) < time.time():
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")
    try:
        claims = oidc.login_with_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OIDC login failed: {e}") from e
    user = crud.find_or_create_oidc_user(
        db, claims["sub"], claims.get("email"), claims.get("name")
    )
    exchange_code = secrets.token_urlsafe(24)
    _oidc_codes[exchange_code] = {
        "user_id": user.user_id,
        "expires": time.time() + 60,
    }
    frontend = __import__("os").getenv("MIRAI_FRONTEND_URL", "http://localhost:8000")
    return RedirectResponse(f"{frontend}/?code={exchange_code}")


@router.post("/oidc/exchange", response_model=schemas.TokenResponse)
def oidc_exchange(
    body: schemas.OidcExchangeRequest,
    db: Session = Depends(get_db),
):
    entry = _oidc_codes.pop(body.code, None)
    if not entry or entry["expires"] < time.time():
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC code")
    user = crud.get_user(db, entry["user_id"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")
    token = create_token(user.user_id, user.username, user.role)
    crud.add_audit_log(db, user.username, "login", "user", user.user_id, "oidc code exchange")
    return schemas.TokenResponse(access_token=token, user=user)
