"""Línea de modo de los servicios que el backend deja en el log al arrancar."""

import logging

import pytest
from django.core.management import call_command
from django.test import override_settings

from config.runtime_services import cache_settings


@override_settings(
    DOCUMENT_STORAGE_BACKEND="filesystem",
    CACHES=cache_settings("database", ""),
    CELERY_TASK_ALWAYS_EAGER=True,
    DOCUMENT_SCANNER="fake",
)
def test_simple_mode_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        call_command("describe_local_services")

    assert caplog.messages == [
        "Servicios locales: almacenamiento=filesystem · caché=database · tareas=inmediatas"
        " · antivirus=fake"
    ]


@override_settings(
    DOCUMENT_STORAGE_BACKEND="s3",
    CACHES=cache_settings("redis", "redis://redis:6379/1"),
    CELERY_TASK_ALWAYS_EAGER=False,
    DOCUMENT_SCANNER="clamd",
)
def test_full_mode_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        call_command("describe_local_services")

    assert caplog.messages == [
        "Servicios locales: almacenamiento=s3 · caché=redis · tareas=worker · antivirus=clamd"
    ]


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}})
def test_unknown_cache_shows_its_class(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        call_command("describe_local_services")

    assert "caché=DummyCache" in caplog.messages[0]
    # Las pruebas usan caché en memoria del proceso.
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    ):
        call_command("describe_local_services")
    assert "caché=memoria" in caplog.messages[1]
