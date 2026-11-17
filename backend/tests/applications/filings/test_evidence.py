"""Evidencia de las respuestas del banco (Parte 3): encolado del análisis, fallas del
almacenamiento y del broker, limpieza del objeto y carreras."""

from collections.abc import Callable
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import FileObject, ScanStatus
from apps.documents.scanning import ScanResult
from apps.documents.storage import MemoryStorage, get_storage
from apps.filings import evidence, tasks
from apps.filings.exceptions import EvidenceAlreadyAttached
from apps.filings.models import Filing, FilingResponse
from tests.applications.filings.test_filings_api import package, ready
from tests.applications.filings.test_responses_api import (
    PDF_BYTES,
    attach,
    filed,
    recorded,
    response_url,
)
from tests.helpers import assert_error

__all__ = ["filed", "package", "ready"]

pytestmark = pytest.mark.django_db


@pytest.fixture
def received(advisor_client: APIClient, filed: Filing) -> FilingResponse:
    return recorded(advisor_client, filed, "RECEIVED")


def evidence_keys() -> list[str]:
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)
    return [key for key in storage.objects if key.startswith("evidence/")]


def stored_status(response: FilingResponse) -> str:
    response.refresh_from_db()
    assert response.evidence_file_object is not None
    return response.evidence_file_object.scan_status


def test_the_scan_is_queued_after_commit(
    advisor_client: APIClient,
    received: FilingResponse,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert attach(advisor_client, received).status_code == 201

    assert len(callbacks) == 1
    # Celery corre en modo inmediato en las pruebas.
    assert stored_status(received) == ScanStatus.CLEAN


def test_a_broker_down_leaves_the_evidence_pending(
    advisor_client: APIClient,
    received: FilingResponse,
    django_capture_on_commit_callbacks: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broker_down(file_object_id: str) -> None:
        raise OperationalError("broker caído")

    monkeypatch.setattr(tasks.scan_filing_evidence, "delay", broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        assert attach(advisor_client, received).status_code == 201

    assert stored_status(received) == ScanStatus.PENDING
    assert "No se pudo encolar el análisis de la evidencia" in caplog.text


def test_storage_down_responds_503(
    advisor_client: APIClient, received: FilingResponse, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(get_storage(), "put", unavailable)

    assert_error(attach(advisor_client, received), 503, "SERVICE_UNAVAILABLE")
    received.refresh_from_db()
    assert received.evidence_file_object is None


@pytest.mark.parametrize("delete_fails", [False, True])
def test_a_failed_attachment_removes_the_stored_object(
    advisor_client: APIClient,
    received: FilingResponse,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    delete_fails: bool,
) -> None:
    """Si otra carga gana la carrera, el objeto guardado se borra (o se avisa si no se
    pudo borrar)."""

    def lost_race(*args: Any, **kwargs: Any) -> None:
        raise EvidenceAlreadyAttached()

    monkeypatch.setattr(evidence, "_attach", lost_race)
    if delete_fails:

        def cannot_delete(key: str) -> None:
            raise StorageUnavailable("sin almacenamiento")

        monkeypatch.setattr(get_storage(), "delete", cannot_delete)

    assert_error(attach(advisor_client, received), 409, "EVIDENCE_ALREADY_ATTACHED")

    if delete_fails:
        assert "No se pudo borrar la evidencia huérfana" in caplog.text
    else:
        assert evidence_keys() == []


def test_the_lock_rejects_a_second_attachment(
    advisor_client: APIClient, received: FilingResponse
) -> None:
    assert attach(advisor_client, received).status_code == 201
    count = FileObject.objects.count()

    with pytest.raises(EvidenceAlreadyAttached):
        evidence._attach(received.pk, {})

    assert FileObject.objects.count() == count


def test_a_scan_that_lost_the_race_keeps_the_first_result(
    advisor_client: APIClient, received: FilingResponse, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert attach(advisor_client, received).status_code == 201
    received.refresh_from_db()
    file_object = received.evidence_file_object
    assert file_object is not None

    def scanned_meanwhile(target: FileObject) -> ScanResult:
        FileObject.objects.filter(pk=target.pk).update(
            scan_status=ScanStatus.INFECTED, scanned_at=target.created_at
        )
        return ScanResult(ScanStatus.CLEAN)

    monkeypatch.setattr(evidence, "inspect_file_object", scanned_meanwhile)

    assert evidence.scan_evidence(file_object.pk) == ScanStatus.INFECTED


def test_an_oversized_body_is_cut_before_reading(
    advisor_client: APIClient, received: FilingResponse
) -> None:
    uploaded = SimpleUploadedFile("respuesta.pdf", PDF_BYTES, content_type="application/pdf")

    response = advisor_client.post(
        response_url(received, "/evidence"),
        {"file": uploaded},
        format="multipart",
        CONTENT_LENGTH=str(50 * 1024 * 1024),
    )

    assert_error(response, 413, "PAYLOAD_TOO_LARGE")
