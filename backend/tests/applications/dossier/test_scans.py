"""Análisis de las versiones cargadas: servicio, tarea con reintentos y
``requeue_pending_scans`` (decisión 3 y acordada 2)."""

import hashlib
import io
import itertools
from collections.abc import Callable
from datetime import timedelta
from typing import Any, BinaryIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.documents import scans, tasks
from apps.documents.constants import PDF
from apps.documents.exceptions import ScannerUnavailable
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    FileObject,
    ScanStatus,
    SlotStatus,
)
from apps.documents.scanning import EICAR, ScanResult
from apps.documents.storage import get_storage
from config import celery_app
from tests.applications.dossier.conftest import (
    DocumentFileFactory,
    FileObjectFactory,
    SlotFactory,
)

pytestmark = pytest.mark.django_db

CLEAN_PDF = b"%PDF-1.7\nlimpio"


def stored(make_file_object: FileObjectFactory, content: bytes = CLEAN_PDF, **extra: Any) -> Any:
    """Objeto físico guardado de verdad en el almacenamiento de pruebas."""
    file_object = make_file_object(
        sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), **extra
    )
    get_storage().put(file_object.object_key, io.BytesIO(content), content_type=PDF)
    return file_object


@pytest.fixture
def current_version(
    make_slot: SlotFactory,
    make_file_object: FileObjectFactory,
    make_document_file: DocumentFileFactory,
) -> Callable[..., DocumentFile]:
    """Versión vigente de un slot ``UPLOADED``, con su archivo pendiente de análisis."""

    created = itertools.count(1)

    def _make(content: bytes = CLEAN_PDF, **extra: Any) -> DocumentFile:
        # Cada llamada es otro slot del mismo juego, para no chocar con la unicidad.
        index = next(created)
        slot = make_slot(status=SlotStatus.UPLOADED, slot_index=index, minimum_files=index)
        version = make_document_file(
            slot=slot, file_object=stored(make_file_object, content), **extra
        )
        ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(current_file=version)
        return version

    return _make


def refreshed(version: DocumentFile) -> tuple[str, str, str]:
    version = DocumentFile.objects.select_related("file_object", "slot").get(pk=version.pk)
    return version.file_object.scan_status, version.status, version.slot.status


def test_clean_moves_the_version_to_review(current_version: Callable[..., DocumentFile]) -> None:
    version = current_version()

    assert scans.scan_document_file(version.file_object_id) == ScanStatus.CLEAN

    assert refreshed(version) == (ScanStatus.CLEAN, "IN_REVIEW", SlotStatus.UPLOADED)


def test_infected_rejects_the_version_and_the_slot(
    current_version: Callable[..., DocumentFile], caplog: pytest.LogCaptureFixture
) -> None:
    version = current_version(b"%PDF-1.4\n" + EICAR)

    assert scans.scan_document_file(version.file_object_id) == ScanStatus.INFECTED

    assert refreshed(version) == (ScanStatus.INFECTED, "REJECTED", SlotStatus.REJECTED)
    assert "Eicar-Test-Signature" in caplog.text
    assert "cedula.pdf" not in caplog.text


def test_a_tampered_object_is_invalid(
    current_version: Callable[..., DocumentFile],
) -> None:
    version = current_version()
    get_storage().put(version.file_object.object_key, io.BytesIO(b"%PDF-otro"), content_type=PDF)

    assert scans.scan_document_file(version.file_object_id) == ScanStatus.INVALID

    assert refreshed(version) == (ScanStatus.INVALID, "REJECTED", SlotStatus.REJECTED)


def test_an_old_version_that_turns_out_infected_does_not_touch_the_slot(
    make_slot: SlotFactory,
    make_file_object: FileObjectFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    slot = make_slot(status=SlotStatus.UPLOADED)
    old = make_document_file(slot=slot, file_object=stored(make_file_object, b"%PDF-1.4\n" + EICAR))
    new = make_document_file(slot=slot, version_number=2)
    ApplicationDocumentSlot.objects.filter(pk=slot.pk).update(current_file=new)

    scans.scan_document_file(old.file_object_id)

    assert refreshed(old) == (ScanStatus.INFECTED, "REJECTED", SlotStatus.UPLOADED)


def test_a_clean_result_keeps_a_decision_already_taken(
    current_version: Callable[..., DocumentFile],
) -> None:
    version = current_version(status=DocumentFileStatus.REJECTED)

    scans.scan_document_file(version.file_object_id)

    assert refreshed(version)[:2] == (ScanStatus.CLEAN, "REJECTED")


def test_scanning_twice_does_nothing(current_version: Callable[..., DocumentFile]) -> None:
    version = current_version()
    scans.scan_document_file(version.file_object_id)
    scanned_at = FileObject.objects.get(pk=version.file_object_id).scanned_at

    assert scans.scan_document_file(version.file_object_id) == ScanStatus.CLEAN
    assert FileObject.objects.get(pk=version.file_object_id).scanned_at == scanned_at


def test_a_result_arriving_after_another_one_is_ignored(
    current_version: Callable[..., DocumentFile],
) -> None:
    """Dos tareas para el mismo archivo: la segunda encuentra el resultado ya guardado."""
    version = current_version()
    FileObject.objects.filter(pk=version.file_object_id).update(
        scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()
    )

    result = scans._apply(version.file_object_id, ScanResult(ScanStatus.INFECTED))

    assert result == ScanStatus.CLEAN
    assert refreshed(version) == (ScanStatus.CLEAN, "UPLOADED", SlotStatus.UPLOADED)


def test_only_document_versions_are_scanned(
    make_file_object: FileObjectFactory, caplog: pytest.LogCaptureFixture
) -> None:
    loose = make_file_object()

    assert scans.scan_document_file(loose.pk) is None
    assert scans.scan_document_file(loose.pk.__class__(int=0)) is None
    assert "no es de una versión" in caplog.text


# --- Tarea ------------------------------------------------------------------------------


@pytest.fixture
def eager_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con ``CELERY_TASK_EAGER_PROPAGATES``, un ``Retry`` se propaga en lugar de volver a
    aplicar la tarea como lo haría un worker. Sin propagar, ``apply`` la reintenta."""
    # La app lee la clave con el prefijo de Django (`namespace="CELERY"`).
    monkeypatch.setitem(celery_app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)


class FailingScanner:
    name = "failing"

    def __init__(self) -> None:
        self.calls = 0

    def scan(self, stream: BinaryIO) -> ScanResult:
        self.calls += 1
        raise ScannerUnavailable("clamd no responde")

    def ping(self) -> None:
        raise ScannerUnavailable("clamd no responde")


def test_the_task_scans_by_id(current_version: Callable[..., DocumentFile]) -> None:
    version = current_version()

    result = tasks.scan_file_object.delay(str(version.file_object_id))

    assert result.get() == ScanStatus.CLEAN


@pytest.mark.usefixtures("eager_retries")
def test_the_task_retries_and_finally_leaves_the_file_pending(
    current_version: Callable[..., DocumentFile],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    version = current_version()
    scanner = FailingScanner()
    monkeypatch.setattr(scans, "get_scanner", lambda: scanner)

    result = tasks.scan_file_object.apply(args=[str(version.file_object_id)])

    assert result.get() == ScanStatus.PENDING
    assert scanner.calls == tasks.SCAN_MAX_RETRIES + 1
    assert refreshed(version) == (ScanStatus.PENDING, "UPLOADED", SlotStatus.UPLOADED)
    assert "queda pendiente" in caplog.text


@pytest.mark.usefixtures("eager_retries")
def test_the_task_also_retries_when_storage_is_down(
    current_version: Callable[..., DocumentFile],
) -> None:
    version = current_version()
    get_storage().delete(version.file_object.object_key)

    result = tasks.scan_file_object.apply(args=[str(version.file_object_id)])

    assert result.get() == ScanStatus.PENDING
    assert refreshed(version)[0] == ScanStatus.PENDING


def test_retry_delay_grows_and_is_capped() -> None:
    delays = [tasks.scan_retry_delay(retries) for retries in range(tasks.SCAN_MAX_RETRIES)]

    assert delays[:5] == [30, 60, 120, 240, 480]
    assert delays[5:] == [900, 900, 900]


# --- requeue_pending_scans --------------------------------------------------------------


def test_requeue_pending_scans_only_takes_old_pending_versions(
    current_version: Callable[..., DocumentFile],
    make_file_object: FileObjectFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = current_version()
    recent = current_version()
    scanned = current_version()
    FileObject.objects.filter(pk=scanned.file_object_id).update(
        scan_status=ScanStatus.CLEAN, scanned_at=timezone.now()
    )
    loose = make_file_object()
    an_hour_ago = timezone.now() - timedelta(hours=1)
    FileObject.objects.filter(pk__in=[old.file_object_id, scanned.file_object_id, loose.pk]).update(
        created_at=an_hour_ago
    )
    queued: list[str] = []
    monkeypatch.setattr(tasks.scan_file_object, "delay", queued.append)

    call_command("requeue_pending_scans")

    assert queued == [str(old.file_object_id)]
    assert "Análisis reencolados: 1." in capsys.readouterr().out

    call_command("requeue_pending_scans", "--older-than-minutes", "0")
    assert set(queued[1:]) == {str(old.file_object_id), str(recent.file_object_id)}
