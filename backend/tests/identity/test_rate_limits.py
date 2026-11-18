"""Límites de consumo (TAREA-brechas-2, parte 3): un solo texto en español para el
`429` y cupos más grandes solo en local (`DEBUG=True` y `AUTH_RATE_LIMIT_MULTIPLIER`)."""

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.identity.throttling import LoginRateThrottle, rate_multiplier
from apps.reporting.throttling import ReportsRateThrottle
from config.exceptions import api_exception_handler, rate_limited_message
from tests.helpers import assert_error, login


def reports_quota() -> int:
    return int(settings.AUTH_RATE_LIMITS["reports"].split("/")[0])


@pytest.mark.parametrize(
    ("wait", "text"),
    [
        (0.2, "1 segundo"),
        (1, "1 segundo"),
        (42.1, "43 segundos"),
        (59.9, "1 minuto"),
        (60, "1 minuto"),
        (61, "2 minutos"),
        (899, "15 minutos"),
        (3600, "60 minutos"),
    ],
)
def test_the_wait_is_rounded_up(wait: float, text: str) -> None:
    assert rate_limited_message(wait) == (
        f"Hiciste demasiados intentos. Vuelve a intentarlo en {text}."
    )


def test_without_a_known_wait_it_says_later() -> None:
    assert rate_limited_message(None) == (
        "Hiciste demasiados intentos. Vuelve a intentarlo más tarde."
    )


def test_every_throttle_uses_the_same_body_and_keeps_retry_after() -> None:
    response = api_exception_handler(Throttled(wait=125), {})

    assert response is not None
    assert response.status_code == 429
    assert response["Retry-After"] == "125"
    assert response.data["code"] == "RATE_LIMITED"
    assert response.data["message"] == (
        "Hiciste demasiados intentos. Vuelve a intentarlo en 3 minutos."
    )
    assert response.data["details"] == []


@pytest.mark.django_db
def test_the_login_429_is_in_spanish(api_client: APIClient, user: User) -> None:
    for _ in range(5):
        assert login(api_client, password="otra-clave").status_code == 401

    body = assert_error(login(api_client), 429, "RATE_LIMITED")

    assert body["message"] == "Hiciste demasiados intentos. Vuelve a intentarlo en 15 minutos."


# --- Multiplicador solo en local --------------------------------------------------------


@override_settings(DEBUG=True, AUTH_RATE_LIMIT_MULTIPLIER=20)
def test_debug_multiplies_every_quota() -> None:
    assert rate_multiplier() == 20
    assert LoginRateThrottle().parse_rate("5/15m") == (100, 900)
    assert ReportsRateThrottle().num_requests == 20 * reports_quota()  # type: ignore[attr-defined]


@override_settings(DEBUG=False, AUTH_RATE_LIMIT_MULTIPLIER=20)
def test_without_debug_the_multiplier_is_ignored() -> None:
    assert rate_multiplier() == 1
    assert LoginRateThrottle().parse_rate("5/15m") == (5, 900)
    assert ReportsRateThrottle().num_requests == reports_quota()  # type: ignore[attr-defined]


@override_settings(DEBUG=True, AUTH_RATE_LIMIT_MULTIPLIER=1)
def test_debug_without_the_variable_keeps_the_quotas() -> None:
    assert LoginRateThrottle().parse_rate("5/15m") == (5, 900)


@pytest.mark.django_db
@override_settings(DEBUG=True, AUTH_RATE_LIMIT_MULTIPLIER=2)
def test_the_login_allows_more_attempts_in_local_debug(api_client: APIClient, user: User) -> None:
    for _ in range(10):
        assert login(api_client, password="otra-clave").status_code == 401

    assert_error(login(api_client), 429, "RATE_LIMITED")
