"""Modo local simple de punta a punta: almacenamiento en disco, caché en la base y tareas
en el mismo proceso (``CELERY_TASK_ALWAYS_EAGER``) sin propagar sus errores, como en
``docker compose up`` sin perfiles. Nada usa Redis ni SeaweedFS.
"""

import io
import logging
import zipfile
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import FileResponse
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents import tasks
from apps.documents.constants import PDF
from apps.documents.exceptions import StorageUnavailable
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentPackageJob,
    PackageJobStatus,
    ScanStatus,
    SlotStatus,
)
from apps.documents.storage import FilesystemStorage, get_storage
from config.celery import app as celery_app
from config.runtime_services import cache_settings
from tests.applications.dossier.conftest import PackageDossier, SlotFactory

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.7\n" + b"contenido de prueba " * 20
DOWNLOAD_PREFIX = "/api/v1/storage/objects/"
Capture = Callable[..., Any]


@pytest.fixture(autouse=True)
def local_mode(
    db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FilesystemStorage]:
    # Como en local: un fallo de la tarea no se propaga a la petición. Con el namespace
    # `CELERY`, Celery lee primero la clave con prefijo.
    monkeypatch.setitem(celery_app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)
    get_storage.cache_clear()
    with override_settings(
        DOCUMENT_STORAGE_BACKEND="filesystem",
        DOCUMENT_STORAGE_ROOT=str(tmp_path / "documents"),
        CACHES=cache_settings("database", ""),
    ):
        call_command("createcachetable", verbosity=0)
        storage = get_storage()
        assert isinstance(storage, FilesystemStorage)
        storage.ensure_bucket()
        yield storage
        get_storage.cache_clear()


@pytest.fixture
def slot(make_slot: SlotFactory) -> ApplicationDocumentSlot:
    return make_slot(validity_days=30)


def upload(client: APIClient, slot: ApplicationDocumentSlot, capture: Capture) -> Any:
    file = SimpleUploadedFile("cédula.pdf", PDF_BYTES, content_type=PDF)
    data = {"file": file, "document_date": timezone.localdate() - timedelta(days=1)}
    with capture(execute=True):
        return client.post(
            f"/api/v1/buyer/document-slots/{slot.id}/uploads", data, format="multipart"
        )


def request_package(client: APIClient, dossier: PackageDossier, capture: Capture) -> Any:
    with capture(execute=True):
        return client.post(f"/api/v1/applications/{dossier.application.id}/document-package-jobs")


def follow(url: str) -> bytes:
    """Sigue la URL firmada como lo haría el navegador: sin sesión."""
    assert url.startswith(DOWNLOAD_PREFIX), url
    response = cast(FileResponse, APIClient().get(url))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    body = response.getvalue()
    response.close()
    return body


def failing_open(key: str) -> BinaryIO:
    raise StorageUnavailable("El almacenamiento no completó open.")


# --- Punta a punta ------------------------------------------------------------------------


def test_upload_scan_review_and_download(
    portal: APIClient,
    advisor_client: APIClient,
    slot: ApplicationDocumentSlot,
    local_mode: FilesystemStorage,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    response = upload(portal, slot, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    version = DocumentFile.objects.select_related("file_object").get(slot=slot)
    file_object = version.file_object
    # El análisis corrió dentro de la petición, con el escáner de prueba.
    assert file_object.scan_status == ScanStatus.CLEAN
    assert version.status == DocumentFileStatus.IN_REVIEW
    assert file_object.storage_provider == "filesystem"
    assert (local_mode.root / file_object.object_key).read_bytes() == PDF_BYTES

    review = advisor_client.patch(
        f"/api/v1/document-slots/{slot.id}/review",
        {"decision": "APPROVED", "document_file_id": str(version.id)},
        format="json",
    )
    assert review.status_code == 200, review.content
    slot.refresh_from_db()
    assert slot.status == SlotStatus.APPROVED

    link = advisor_client.get(f"/api/v1/document-files/{version.id}/download")
    assert link.status_code == 200, link.content
    assert follow(link.json()["url"]) == PDF_BYTES


def test_package_is_built_inline_and_downloaded(
    advisor_client: APIClient,
    package_dossier: PackageDossier,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    response = request_package(advisor_client, package_dossier, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    job = DocumentPackageJob.objects.get(pk=response.json()["id"])
    assert job.status == PackageJobStatus.COMPLETED
    link = advisor_client.get(f"/api/v1/document-package-jobs/{job.id}/download")
    assert link.status_code == 200, link.content
    with zipfile.ZipFile(io.BytesIO(follow(link.json()["url"]))) as archive:
        contents = {archive.read(name) for name in archive.namelist()}
    assert set(package_dossier.contents.values()) <= contents


# --- Fallos en modo inmediato ---------------------------------------------------------------


def test_scan_with_storage_down_leaves_the_file_pending(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    local_mode: FilesystemStorage,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    monkeypatch.setattr(local_mode, "open", failing_open)  # Guardar sí funciona.

    response = upload(portal, slot, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    file_object = DocumentFile.objects.select_related("file_object").get(slot=slot).file_object
    # Los reintentos corren seguidos y al agotarse el archivo queda para requeue_pending_scans.
    assert file_object.scan_status == ScanStatus.PENDING
    assert f"Análisis del archivo {file_object.id} sin completar tras 8 reintentos" in caplog.text


def test_package_with_storage_down_fails_without_breaking_the_request(
    advisor_client: APIClient,
    package_dossier: PackageDossier,
    local_mode: FilesystemStorage,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    monkeypatch.setattr(local_mode, "open", failing_open)

    response = request_package(advisor_client, package_dossier, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    job = DocumentPackageJob.objects.get(pk=response.json()["id"])
    assert job.status == PackageJobStatus.FAILED
    assert job.error_code == "STORAGE_UNAVAILABLE"


def test_an_unexpected_scan_error_is_logged_and_the_upload_succeeds(
    portal: APIClient,
    slot: ApplicationDocumentSlot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    def broken(file_object_id: Any) -> str:
        raise RuntimeError("error inesperado")

    monkeypatch.setattr(tasks, "scan_document_file", broken)

    response = upload(portal, slot, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    file_object = DocumentFile.objects.select_related("file_object").get(slot=slot).file_object
    assert file_object.scan_status == ScanStatus.PENDING
    assert_logged_exception(caplog, f"Análisis del archivo {file_object.id} falló")


def test_an_unexpected_package_error_is_logged_and_the_request_succeeds(
    advisor_client: APIClient,
    package_dossier: PackageDossier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Capture,
) -> None:
    def broken(job_id: Any, *, last_attempt: bool) -> str:
        raise RuntimeError("error inesperado")

    monkeypatch.setattr(tasks, "build_package", broken)

    response = request_package(advisor_client, package_dossier, django_capture_on_commit_callbacks)

    assert response.status_code == 201, response.content
    job = DocumentPackageJob.objects.get(pk=response.json()["id"])
    assert job.status == PackageJobStatus.PENDING
    assert_logged_exception(caplog, f"Paquete {job.id} falló")


def assert_logged_exception(caplog: pytest.LogCaptureFixture, message: str) -> None:
    records = [
        record
        for record in caplog.records
        if record.name == "apps.documents.tasks" and record.getMessage().startswith(message)
    ]
    assert len(records) == 1, caplog.text
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
    assert isinstance(records[0].exc_info[1], RuntimeError)
