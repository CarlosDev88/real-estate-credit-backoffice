"""Autenticación interna: lo que ``tests/identity`` no cubre (``specs/TAREA-seguridad.md``,
Parte 4.1).

Lo que ya prueban ``tests/identity/test_sessions.py``, ``test_passwords.py`` y
``test_login.py`` (firma alterada, ``alg=none``, otra clave, otra audiencia, rotación y
reuso del refresh, logout, CSRF ausente, restablecimiento de un solo uso y vencido, Argon2)
no se repite aquí.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from smtplib import SMTPException
from typing import Any
from unittest import mock

import jwt
import pytest
from django.conf import settings
from django.contrib.auth.hashers import Argon2PasswordHasher
from django.core.mail.backends.base import BaseEmailBackend
from django.db import transaction
from django.test import override_settings
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.identity.cookies import access_cookie_name
from apps.identity.models import User
from tests.helpers import (
    ME_URL,
    PASSWORD_RESET_REQUEST_URL,
    access_cookie,
    csrf_token,
    login,
)

pytestmark = pytest.mark.django_db


def _claims(client: APIClient) -> dict[str, Any]:
    return dict(jwt.decode(access_cookie(client), options={"verify_signature": False}))


def _forge(client: APIClient, algorithm: str = "HS256", **changes: Any) -> None:
    claims = {**_claims(client), **changes}
    for key, value in list(claims.items()):
        if value is None:
            del claims[key]
    token = jwt.encode(claims, settings.AUTH_JWT_SIGNING_KEY, algorithm=algorithm)
    client.cookies[access_cookie_name()] = token


# --- JWT: algoritmo y claims ---------------------------------------------------------


# La clave de pruebas es corta para HS512: PyJWT avisa, y aquí no importa.
@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize(
    ("label", "algorithm", "changes"),
    [
        ("otro algoritmo HMAC con la misma clave", "HS512", {}),
        ("otro emisor", "HS256", {"iss": "otra-api"}),
        ("otro tipo de token", "HS256", {"typ": "refresh"}),
        ("sin sid", "HS256", {"sid": None}),
        ("sin jti", "HS256", {"jti": None}),
        ("sin exp", "HS256", {"exp": None}),
        ("sid de otra sesión", "HS256", {"sid": "00000000-0000-0000-0000-000000000000"}),
        ("sub de otro usuario", "HS256", {"sub": "00000000-0000-0000-0000-000000000000"}),
    ],
)
def test_forged_access_token_is_rejected(
    logged_client: APIClient, label: str, algorithm: str, changes: dict[str, Any]
) -> None:
    _forge(logged_client, algorithm, **changes)
    response = logged_client.get(ME_URL)
    assert response.status_code == 401, label


def test_access_token_signed_with_secret_key_is_rejected(logged_client: APIClient) -> None:
    """La firma usa ``AUTH_JWT_SIGNING_KEY``; un token firmado con ``SECRET_KEY`` no sirve."""
    token = jwt.encode(_claims(logged_client), settings.SECRET_KEY, algorithm="HS256")
    logged_client.cookies[access_cookie_name()] = token
    assert logged_client.get(ME_URL).status_code == 401


def test_jwt_leeway_is_five_seconds(api_client: APIClient, user: User) -> None:
    assert settings.AUTH_JWT_LEEWAY_SECONDS == 5
    with freeze_time() as frozen:
        assert login(api_client).status_code == 200
        frozen.tick(settings.AUTH_ACCESS_TOKEN_LIFETIME + timedelta(seconds=4))
        assert api_client.get(ME_URL).status_code == 200
        frozen.tick(timedelta(seconds=2))
        assert api_client.get(ME_URL).status_code == 401


def test_signing_key_has_no_default() -> None:
    """``base.py`` exige la clave del entorno (``env("AUTH_JWT_SIGNING_KEY")``, sin
    ``default``): sin ella la API no arranca. Aquí, que no sea la ``SECRET_KEY``."""
    assert settings.AUTH_JWT_SIGNING_KEY
    assert settings.AUTH_JWT_SIGNING_KEY != settings.SECRET_KEY


# --- CSRF ------------------------------------------------------------------------------


def test_write_with_another_csrf_token_is_rejected(csrf_client: APIClient, user: User) -> None:
    assert login(csrf_client).status_code == 200
    real = csrf_token(csrf_client)
    other = ("x" if real[0] != "x" else "y") + real[1:]
    response = csrf_client.post("/api/v1/clients", {}, format="json", HTTP_X_CSRFTOKEN=other)
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_write_with_the_right_csrf_token_reaches_validation(
    csrf_client: APIClient, make_user: Callable[..., User]
) -> None:
    make_user(email="asesora@example.com", permissions=["clients.create"])
    assert login(csrf_client, email="asesora@example.com").status_code == 200
    response = csrf_client.post(
        "/api/v1/clients", {}, format="json", HTTP_X_CSRFTOKEN=csrf_token(csrf_client)
    )
    assert response.status_code == 400


# --- Contraseñas -------------------------------------------------------------------------


def test_production_hasher_meets_the_owasp_minimum() -> None:
    """REQ §9.1: Argon2id con al menos 19 MiB, 2 iteraciones y paralelismo 1 (las pruebas
    usan MD5 por velocidad; esto revisa el hasher que configura ``base.py``)."""
    hasher = Argon2PasswordHasher()
    encoded = hasher.encode("Clave-De-Prueba-2026", hasher.salt())
    assert encoded.startswith("argon2$argon2id$")
    assert hasher.memory_cost >= 19 * 1024
    assert hasher.time_cost >= 2
    assert hasher.parallelism >= 1


@pytest.mark.parametrize(
    "password",
    ["corta1!", "12345678901", "password123", "asesor@example.com"],
    ids=["corta", "solo-numeros", "comun", "parecida-al-usuario"],
)
def test_weak_passwords_are_rejected(logged_client: APIClient, password: str) -> None:
    response = logged_client.post(
        "/api/v1/auth/change-password",
        {"current_password": "Clave-Segura-2026!", "new_password": password},
        format="json",
    )
    assert response.status_code == 400, response.content


# --- Enumeración por la recuperación -------------------------------------------------


class _FailingEmailBackend(BaseEmailBackend):
    """Un SMTP caído."""

    def send_messages(self, email_messages: Any) -> int:
        raise SMTPException("SMTP caído")


@pytest.fixture
def commit_callbacks_run_now() -> Iterator[None]:
    """Como en producción: al cerrar la transacción del servicio, ``on_commit`` corre ya,
    dentro de la misma petición (en las pruebas, la transacción de ``TestCase`` lo
    impediría)."""

    def run_now(func: Callable[[], Any], using: str | None = None, robust: bool = False) -> None:
        func()

    with mock.patch.object(transaction, "on_commit", run_now):
        yield


@pytest.mark.xfail(strict=True, reason="SEC-14")
@override_settings(EMAIL_BACKEND="tests.security.test_auth._FailingEmailBackend")
def test_reset_request_answers_the_same_when_the_mail_fails(
    api_client: APIClient, user: User, commit_callbacks_run_now: None
) -> None:
    """Con el correo caído, la respuesta para un usuario que existe debe ser la misma que
    para uno que no existe (202). Hoy el correo se envía en la misma petición y la
    excepción solo sale cuando el usuario existe."""
    unknown = api_client.post(PASSWORD_RESET_REQUEST_URL, {"email": "nadie@example.com"})
    assert unknown.status_code == 202
    try:
        known = api_client.post(PASSWORD_RESET_REQUEST_URL, {"email": user.email})
        known_status = known.status_code
    except SMTPException:
        known_status = 500
    assert known_status == unknown.status_code
