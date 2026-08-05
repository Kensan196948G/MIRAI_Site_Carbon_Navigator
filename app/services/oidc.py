"""Minimal OIDC authorization-code flow (stdlib + PyJWT)."""
import json
import os
from typing import Optional
from urllib import parse, request

import jwt


def oidc_enabled() -> bool:
    return bool(os.getenv("MIRAI_OIDC_ISSUER") and os.getenv("MIRAI_OIDC_CLIENT_ID"))


def _discover() -> dict:
    issuer = os.getenv("MIRAI_OIDC_ISSUER").rstrip("/")
    with request.urlopen(f"{issuer}/.well-known/openid-configuration", timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def authorization_url(state: str) -> str:
    config = _discover()
    params = parse.urlencode({
        "response_type": "code",
        "client_id": os.getenv("MIRAI_OIDC_CLIENT_ID"),
        "redirect_uri": os.getenv("MIRAI_OIDC_REDIRECT_URI"),
        "scope": "openid email profile",
        "state": state,
    })
    return f"{config['authorization_endpoint']}?{params}"


def exchange_code(code: str) -> dict:
    config = _discover()
    payload = parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv("MIRAI_OIDC_REDIRECT_URI"),
        "client_id": os.getenv("MIRAI_OIDC_CLIENT_ID"),
        "client_secret": os.getenv("MIRAI_OIDC_CLIENT_SECRET", ""),
    }).encode()
    req = request.Request(
        config["token_endpoint"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_id_token(id_token: str) -> dict:
    unverified = jwt.decode(id_token, options={"verify_signature": False})
    config = _discover()
    with request.urlopen(config["jwks_uri"], timeout=15) as resp:
        jwks = json.loads(resp.read().decode("utf-8"))
    kid = unverified.get("kid")
    jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not jwk:
        raise ValueError("No matching JWK")
    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    return jwt.decode(
        id_token,
        key=key,
        algorithms=["RS256"],
        audience=os.getenv("MIRAI_OIDC_CLIENT_ID"),
        issuer=os.getenv("MIRAI_OIDC_ISSUER").rstrip("/"),
        options={"require": ["exp", "iat"]},
    )


def login_with_code(code: str) -> dict:
    tokens = exchange_code(code)
    id_token = tokens.get("id_token")
    if not id_token:
        raise ValueError("No id_token in OIDC response")
    claims = verify_id_token(id_token)
    return {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "name": claims.get("name") or claims.get("preferred_username"),
    }
