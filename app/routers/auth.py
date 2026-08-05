import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, body.username)
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
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
    token = create_token(user.user_id, user.username, user.role)
    frontend = __import__("os").getenv("MIRAI_FRONTEND_URL", "http://localhost:8000")
    return RedirectResponse(f"{frontend}/?token={token}")
