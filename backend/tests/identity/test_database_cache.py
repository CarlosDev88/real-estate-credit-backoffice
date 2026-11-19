"""Límites de consumo con ``CACHE_BACKEND=database`` (modo local simple, sin Redis)."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.models import User
from config.runtime_services import CACHE_TABLE, cache_settings
from tests.helpers import assert_error, login


@pytest.fixture
def database_cache(db: Any) -> Iterator[None]:
    with override_settings(CACHES=cache_settings("database", "")):
        call_command("createcachetable", verbosity=0)
        cache.clear()
        yield


def cached_rows() -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {CACHE_TABLE}")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def test_login_rate_limit_lives_in_the_database(
    database_cache: None, api_client: APIClient, user: User
) -> None:
    for _ in range(5):
        assert login(api_client, password="otra-clave").status_code == 401

    response = login(api_client)  # Incluso con la contraseña correcta.

    assert_error(response, 429, "RATE_LIMITED")
    assert int(response["Retry-After"]) > 0
    # Los contadores están en la tabla compartida, no en la memoria de este proceso: IP +
    # correo, IP sola, correo solo (SEC-09) y el general de escrituras por IP (SEC-10).
    assert cached_rows() == 4
    # Otro correo desde la misma IP tiene sus propios contadores de IP + correo y de correo.
    assert login(api_client, email="otro@example.com").status_code == 401
    assert cached_rows() == 6


def test_createcachetable_can_run_again(database_cache: None) -> None:
    call_command("createcachetable", verbosity=0)

    cache.set("clave", "valor")
    assert cache.get("clave") == "valor"
