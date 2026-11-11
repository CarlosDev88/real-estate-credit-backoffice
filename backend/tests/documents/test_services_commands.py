"""Comandos de los servicios del expediente y configuración de Celery."""

from io import StringIO
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.management import CommandError, call_command

from apps.documents.exceptions import ScannerUnavailable, StorageUnavailable
from config import celery_app

STORAGE = "apps.documents.management.commands.{}.get_storage"
SCANNER = "apps.documents.management.commands.check_document_services.get_scanner"


def run(command: str) -> str:
    out = StringIO()
    call_command(command, stdout=out)
    return out.getvalue()


def stub(**extra: Any) -> MagicMock:
    service = MagicMock(**extra)
    service.provider = "s3"
    service.bucket = "mvp-credit-documents"
    service.name = "clamd"
    return service


def test_init_document_storage_reports_whether_it_created_the_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "ya existía" in run("init_document_storage")

    storage = stub()
    storage.ensure_bucket.return_value = True
    monkeypatch.setattr(STORAGE.format("init_document_storage"), lambda: storage)
    assert "mvp-credit-documents: creado" in run("init_document_storage")


def test_init_document_storage_fails_when_storage_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = stub()
    storage.ensure_bucket.side_effect = StorageUnavailable("sin conexión")
    monkeypatch.setattr(STORAGE.format("init_document_storage"), lambda: storage)

    with pytest.raises(CommandError, match="mvp-credit-documents"):
        run("init_document_storage")


def test_check_document_services_ok_with_the_test_doubles() -> None:
    output = run("check_document_services")

    assert "Almacenamiento (memory, memory-bucket): OK" in output
    assert "Antivirus (fake): OK" in output


def test_check_document_services_lists_every_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = stub()
    storage.check.side_effect = StorageUnavailable("el bucket no responde")
    scanner = stub()
    scanner.ping.side_effect = ScannerUnavailable("clamd no responde")
    monkeypatch.setattr(STORAGE.format("check_document_services"), lambda: storage)
    monkeypatch.setattr(SCANNER, lambda: scanner)

    with pytest.raises(CommandError) as error:
        run("check_document_services")

    assert "el bucket no responde" in str(error.value)
    assert "clamd no responde" in str(error.value)


def test_celery_reads_django_settings() -> None:
    assert celery_app.main == "config"
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
