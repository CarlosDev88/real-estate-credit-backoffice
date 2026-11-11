"""Cookies de sesión interna y del comprador (sección 4.1 de la especificación).

Con ``AUTH_COOKIE_SECURE`` activo, los nombres llevan el prefijo ``__Host-``, que el
navegador solo acepta con ``Secure``, ``Path=/`` y sin ``Domain``. En desarrollo local
sobre HTTP se omite el prefijo, porque el navegador rechazaría la cookie.
"""

import math
from datetime import datetime
from typing import Literal, cast

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

SameSite = Literal["Lax", "Strict", "None"]

ACCESS_COOKIE_BASE_NAME = "app_access"
REFRESH_COOKIE_BASE_NAME = "app_refresh"
BUYER_SESSION_COOKIE_BASE_NAME = "buyer_session"


def _cookie_name(base_name: str) -> str:
    return f"__Host-{base_name}" if settings.AUTH_COOKIE_SECURE else base_name


def access_cookie_name() -> str:
    return _cookie_name(ACCESS_COOKIE_BASE_NAME)


def refresh_cookie_name() -> str:
    return _cookie_name(REFRESH_COOKIE_BASE_NAME)


def buyer_session_cookie_name() -> str:
    return _cookie_name(BUYER_SESSION_COOKIE_BASE_NAME)


def _samesite() -> SameSite:
    return cast(SameSite, settings.AUTH_COOKIE_SAMESITE)


def _set_cookie(response: HttpResponse, name: str, value: str, expires_at: datetime) -> None:
    max_age = max(math.ceil((expires_at - timezone.now()).total_seconds()), 0)
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=_samesite(),
    )


def set_session_cookies(
    response: HttpResponse,
    *,
    access_token: str,
    access_expires_at: datetime,
    refresh_token: str,
    refresh_expires_at: datetime,
) -> None:
    _set_cookie(response, access_cookie_name(), access_token, access_expires_at)
    _set_cookie(response, refresh_cookie_name(), refresh_token, refresh_expires_at)


def clear_session_cookies(response: HttpResponse) -> None:
    for name in (access_cookie_name(), refresh_cookie_name()):
        response.delete_cookie(name, path="/", samesite=_samesite())


def set_buyer_session_cookie(response: HttpResponse, *, token: str, expires_at: datetime) -> None:
    _set_cookie(response, buyer_session_cookie_name(), token, expires_at)


def clear_buyer_session_cookie(response: HttpResponse) -> None:
    response.delete_cookie(buyer_session_cookie_name(), path="/", samesite=_samesite())
