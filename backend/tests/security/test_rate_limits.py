"""Límites de consumo (SEC-09 y SEC-10, Fase B).

- SEC-09: login y recuperación suman, al límite por IP + correo, uno por IP sobre todos
  los correos (rociado) y uno por correo sobre todas las IP (fuerza bruta distribuida).
- SEC-10: límites generales de lecturas y escrituras por usuario, sesión del comprador o
  IP, y un cupo común de cambios de estado, radicaciones y desistimientos.

``config/settings/test.py`` sube las tasas generales ×1000 para el resto de la suite;
aquí se vuelve a las reales (``base.AUTH_RATE_LIMITS``) o se bajan para no hacer 600
peticiones.
"""

from collections.abc import Callable
from typing import Any

import pytest
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.identity.throttling import GENERAL_THROTTLES
from config.settings import base
from tests.helpers import (
    DEFAULT_PASSWORD,
    LOGIN_URL,
    ME_URL,
    PASSWORD_RESET_CONFIRM_URL,
    PASSWORD_RESET_REQUEST_URL,
    assert_error,
)
from tests.security.conftest import ADVISOR_OWNER, BUYER_OWNER, World
from tests.security.requests import client_for

pytestmark = pytest.mark.django_db

API = "/api/v1"
RATE_LIMITED_TEXT = "Hiciste demasiados intentos. Vuelve a intentarlo en"


def _limits(**rates: str) -> Any:
    return override_settings(AUTH_RATE_LIMITS={**base.AUTH_RATE_LIMITS, **rates})


def _login(client: APIClient, email: str, ip: str, password: str = "mal-password-1") -> Any:
    return client.post(LOGIN_URL, {"email": email, "password": password}, REMOTE_ADDR=ip)


def _reset(client: APIClient, email: str, ip: str) -> Any:
    with TestCase.captureOnCommitCallbacks(execute=True):
        return client.post(PASSWORD_RESET_REQUEST_URL, {"email": email}, REMOTE_ADDR=ip)


def _assert_rate_limited(response: Any) -> dict[str, Any]:
    body = assert_error(response, 429, "RATE_LIMITED")
    assert int(response["Retry-After"]) > 0
    assert body["message"].startswith(RATE_LIMITED_TEXT), body
    return body


def _without_request_id(body: dict[str, Any]) -> dict[str, Any]:
    """El cuerpo sin lo que cambia en cada petición: el ``request_id`` y los minutos del
    texto, que dependen del reloj (el de la VM de Docker salta unos segundos). Que los
    dos textos sean el del ``429`` en español ya lo revisa ``_assert_rate_limited``."""
    return {**body, "request_id": "-", "message": "-"}


# --- SEC-09: login y recuperación ----------------------------------------------------


def test_login_rates_are_the_agreed_ones() -> None:
    limits = base.AUTH_RATE_LIMITS
    assert (limits["login"], limits["login_ip"], limits["login_account"]) == (
        "5/15m",
        "20/15m",
        "10/15m",
    )
    assert (
        limits["password_reset_request"],
        limits["password_reset_request_ip"],
        limits["password_reset_request_account"],
    ) == ("3/1h", "10/1h", "5/1h")


@_limits()
def test_password_spraying_from_one_ip_is_limited(api_client: APIClient, user: User) -> None:
    """Una contraseña contra 20 correos distintos desde la misma IP: el 21.º es 429, sea
    el correo de una cuenta que existe o no."""
    for index in range(20):
        assert _login(api_client, f"usuario{index}@example.com", "10.0.0.1").status_code == 401
    unknown = _assert_rate_limited(_login(api_client, "nadie@example.com", "10.0.0.1"))
    known = _assert_rate_limited(_login(api_client, user.email, "10.0.0.1", DEFAULT_PASSWORD))
    assert _without_request_id(known) == _without_request_id(unknown)
    # Otra IP no está afectada.
    assert _login(api_client, user.email, "10.0.0.2", DEFAULT_PASSWORD).status_code == 200


@_limits()
def test_one_account_from_many_ips_is_limited(api_client: APIClient, user: User) -> None:
    """Fuerza bruta distribuida: 10 fallos sobre la misma cuenta desde 5 IP (2 por IP,
    por debajo del límite por IP + correo); desde una IP nueva, ni la contraseña correcta
    entra hasta que pase la ventana. Igual para un correo que no existe."""
    for index in range(10):
        assert _login(api_client, user.email, f"10.0.1.{index // 2}").status_code == 401
    known = _assert_rate_limited(_login(api_client, user.email, "10.0.2.1", DEFAULT_PASSWORD))

    for index in range(10):
        assert _login(api_client, "nadie@example.com", f"10.0.3.{index // 2}").status_code == 401
    unknown = _assert_rate_limited(_login(api_client, "nadie@example.com", "10.0.4.1"))
    assert _without_request_id(known) == _without_request_id(unknown)

    # El límite es de esa cuenta: otra cuenta, desde la misma IP nueva, entra.
    other = User.objects.create_user(email="otra@example.com", password=DEFAULT_PASSWORD)
    assert _login(api_client, other.email, "10.0.2.1", DEFAULT_PASSWORD).status_code == 200


@_limits()
def test_reset_requests_to_many_emails_from_one_ip_are_limited(
    api_client: APIClient, user: User
) -> None:
    for index in range(10):
        assert _reset(api_client, f"r{index}@example.com", "10.0.5.1").status_code == 202
    _assert_rate_limited(_reset(api_client, user.email, "10.0.5.1"))


@_limits()
def test_reset_requests_to_one_email_from_many_ips_are_limited(
    api_client: APIClient, user: User
) -> None:
    """Bombardeo de correos a una víctima desde varias IP: 5 por hora como mucho."""
    for index in range(5):
        assert _reset(api_client, user.email, f"10.0.6.{index}").status_code == 202
    known = _assert_rate_limited(_reset(api_client, user.email, "10.0.6.9"))
    assert len(mail.outbox) == 5

    for index in range(5):
        assert _reset(api_client, "nadie@example.com", f"10.0.7.{index}").status_code == 202
    unknown = _assert_rate_limited(_reset(api_client, "nadie@example.com", "10.0.7.9"))
    assert _without_request_id(known) == _without_request_id(unknown)


# --- SEC-10: límites generales ---------------------------------------------------------


def test_general_rates_are_the_ones_of_the_requirements() -> None:
    """REQUERIMIENTOS §9.3 y API §26: 600 lecturas, 120 escrituras y 20 cambios de estado
    o radicaciones por minuto."""
    limits = base.AUTH_RATE_LIMITS
    assert (limits["general_read"], limits["general_write"], limits["state_changes"]) == (
        "600/1m",
        "120/1m",
        "20/1m",
    )
    assert [f"{c.__module__}.{c.__name__}" for c in GENERAL_THROTTLES] == list(
        base.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
    )
    assert api_settings.DEFAULT_THROTTLE_CLASSES == GENERAL_THROTTLES


@_limits(general_read="3/1m")
def test_reads_are_limited_per_user(
    logged_client: APIClient, make_user: Callable[..., User]
) -> None:
    for _ in range(3):
        assert logged_client.get(ME_URL).status_code == 200
    _assert_rate_limited(logged_client.get(ME_URL))
    # Las escrituras tienen su propio cupo, y otro usuario el suyo.
    other_user = make_user(email="otro@example.com")
    other = APIClient()
    login = other.post(LOGIN_URL, {"email": other_user.email, "password": DEFAULT_PASSWORD})
    assert login.status_code == 200
    assert other.get(ME_URL).status_code == 200


@_limits(general_write="3/1m")
def test_writes_without_session_are_limited_per_ip(api_client: APIClient) -> None:
    url = PASSWORD_RESET_CONFIRM_URL
    body = {"token": "x" * 43, "new_password": "Una-Clave-Larga-2031"}
    for _ in range(3):
        assert api_client.post(url, body, REMOTE_ADDR="10.0.8.1").status_code == 400
    _assert_rate_limited(api_client.post(url, body, REMOTE_ADDR="10.0.8.1"))
    assert api_client.post(url, body, REMOTE_ADDR="10.0.8.2").status_code == 400


@_limits(general_read="3/1m")
def test_buyer_reads_are_limited_per_session(world: World) -> None:
    client = client_for(world, BUYER_OWNER)
    for _ in range(3):
        assert client.get(f"{API}/buyer/session").status_code == 200
    _assert_rate_limited(client.get(f"{API}/buyer/session"))


@_limits(general_write="3/1m")
def test_writes_are_limited_per_user(world: World) -> None:
    """Escrituras inválidas también cuentan: el límite va antes de la validación."""
    client = client_for(world, ADVISOR_OWNER)
    for _ in range(3):
        assert client.post(f"{API}/clients", {}, format="json").status_code != 429
    _assert_rate_limited(client.post(f"{API}/clients", {}, format="json"))
    # Las lecturas siguen.
    assert client.get(f"{API}/clients").status_code == 200


@_limits()
def test_state_changes_share_a_quota_of_twenty_per_minute(world: World) -> None:
    """Cambios de estado, desistimientos y radicaciones comparten el cupo de 20."""
    client = client_for(world, ADVISOR_OWNER)
    application = world.a.application.pk
    urls = [
        f"{API}/applications/{application}/status-transitions",
        f"{API}/applications/{application}/withdrawals",
        f"{API}/applications/{application}/filings",
    ]
    for index in range(20):
        response = client.post(urls[index % 3], {}, format="json")
        assert response.status_code != 429, (index, response.content)
    for url in urls:
        _assert_rate_limited(client.post(url, {}, format="json"))
    # Las demás escrituras y las lecturas no están afectadas.
    assert client.post(f"{API}/clients", {}, format="json").status_code != 429
    assert client.get(urls[2]).status_code == 200


def _views() -> list[Any]:
    found: list[Any] = []

    def walk(patterns: list[Any], prefix: str) -> None:
        for pattern in patterns:
            route = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, route)
            elif isinstance(pattern, URLPattern):
                view_class = getattr(pattern.callback, "view_class", None)
                if view_class is not None and route.startswith("api/"):
                    found.append(view_class)

    walk(get_resolver().url_patterns, "")
    return found


# Sin límites generales a propósito: el enlace firmado del almacenamiento local en disco
# (solo con servicios falsos); su emisión ya cuenta como descarga.
EXEMPT_VIEWS = {"StorageObjectView"}


def test_every_api_view_keeps_the_general_limits() -> None:
    """Una vista con límites propios los suma a los generales, no los reemplaza."""
    views = _views()
    assert len(views) > 50
    missing = sorted(
        view.__name__
        for view in views
        if view.__name__ not in EXEMPT_VIEWS
        and not set(GENERAL_THROTTLES) <= set(view.throttle_classes)
    )
    assert missing == []


def test_state_change_views_declare_the_shared_scope() -> None:
    scoped = sorted(
        view.__name__
        for view in _views()
        if getattr(view, "throttle_scope", None) == "state_changes"
    )
    assert scoped == [
        "ApplicationFilingListView",
        "ApplicationStatusTransitionView",
        "ApplicationWithdrawalView",
        "OpportunityTransitionView",
    ]
