"""Generación y verificación de tokens de autenticación interna.

- Access token: JWT HS256 de corta duración. Lleva el ``sid`` de la sesión para que
  cerrar o revocar la sesión corte el acceso de inmediato.
- Refresh token y token de recuperación: valores opacos de 256 bits. En la base de
  datos solo se guarda su hash SHA-256.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jwt
from django.conf import settings
from django.utils import timezone

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
_REQUIRED_CLAIMS = ["exp", "iat", "nbf", "iss", "aud", "sub", "jti", "sid", "typ"]


class InvalidAccessToken(Exception):
    """El JWT está vencido, alterado o no fue emitido por esta API."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    jti: str
    expires_at: datetime


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_access_token(*, user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, datetime]:
    now = timezone.now()
    expires_at = now + settings.AUTH_ACCESS_TOKEN_LIFETIME
    payload: dict[str, Any] = {
        "iss": settings.AUTH_JWT_ISSUER,
        "aud": settings.AUTH_JWT_AUDIENCE,
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": uuid.uuid4().hex,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.AUTH_JWT_SIGNING_KEY, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.AUTH_JWT_SIGNING_KEY,
            algorithms=[JWT_ALGORITHM],
            audience=settings.AUTH_JWT_AUDIENCE,
            issuer=settings.AUTH_JWT_ISSUER,
            options={"require": _REQUIRED_CLAIMS},
            leeway=settings.AUTH_JWT_LEEWAY_SECONDS,
        )
        if payload["typ"] != ACCESS_TOKEN_TYPE:
            raise InvalidAccessToken("Tipo de token no permitido.")
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            jti=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidAccessToken(str(exc)) from exc
