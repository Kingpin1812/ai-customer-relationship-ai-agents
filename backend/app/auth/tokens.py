"""Identity verification. Dev tokens and OIDC tokens never share a code path or a key."""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.errors import Unauthenticated

_jwks_client: jwt.PyJWKClient | None = None


def issue_dev_token(subject: str) -> tuple[str, int]:
    settings = get_settings()
    ttl = settings.jwt_ttl_minutes * 60
    token = jwt.encode(
        {"sub": subject, "exp": datetime.now(UTC) + timedelta(seconds=ttl), "iss": "dev-auth"},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, ttl


def _verify_dev(token: str) -> dict:
    return jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=["HS256"],
        issuer="dev-auth",
        options={"require": ["exp", "sub", "iss"]},
    )


def _verify_oidc(token: str) -> dict:
    global _jwks_client
    settings = get_settings()
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.oidc_jwks_url or "")
    key = _jwks_client.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "sub", "iss", "aud"]},
    )


def verify_token(token: str) -> str:
    """Return the identity subject, or raise Unauthenticated."""
    try:
        claims = _verify_dev(token) if get_settings().auth_mode == "dev" else _verify_oidc(token)
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Your session has expired or is invalid.") from exc
    return claims["sub"]
