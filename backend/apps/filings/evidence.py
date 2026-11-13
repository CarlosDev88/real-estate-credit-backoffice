"""Evidencia de una respuesta del banco (paso 11).

- **Carga** (``attach_evidence``): un archivo PDF, JPG o PNG de hasta
  ``EVIDENCE_MAX_BYTES``, validado igual que los documentos (``inspect_upload``: tipo
  real, extensión y tamaño). Se guarda en el almacenamiento configurado como un
  ``FileObject`` ``PENDING`` y se encola el mismo análisis antivirus. Una sola vez por
  respuesta (``409 EVIDENCE_ALREADY_ATTACHED``); la carga quien registró la respuesta o
  un administrador.
- **Análisis** (``scan_evidence``): el mismo de los documentos
  (``scans.inspect_file_object``); solo cambia el estado del archivo.
- **Descarga** (``evidence_download``): URL firmada de ``documents.downloads``, solo si el
  análisis la dejó ``CLEAN`` (``409 FILE_NOT_CLEAN``).
"""

import logging
import uuid
from functools import partial
from typing import BinaryIO

from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.exceptions import PermissionDenied

from apps.applications.services import get_application_scope
from apps.documents.constants import JPEG, PDF, PNG
from apps.documents.downloads import DownloadLink, file_object_link
from apps.documents.exceptions import StorageUnavailable, UploadUnavailable
from apps.documents.file_validation import inspect_upload
from apps.documents.models import FileObject, ScanStatus
from apps.documents.scans import inspect_file_object
from apps.documents.storage import get_storage
from apps.filings.exceptions import EvidenceAlreadyAttached
from apps.filings.models import FilingResponse
from apps.identity.models import User

logger = logging.getLogger(__name__)

EVIDENCE_MIME_TYPES = (PDF, JPEG, PNG)
EVIDENCE_MAX_BYTES = 10 * 1024 * 1024
EVIDENCE_PREFIX = "evidence"


def new_evidence_key(application_id: uuid.UUID) -> str:
    return f"{EVIDENCE_PREFIX}/{application_id}/{uuid.uuid4()}"


def ensure_can_attach(user: User, response: FilingResponse) -> None:
    """Quien registró la respuesta o un administrador."""
    if response.recorded_by_id != user.pk and not get_application_scope(user).sees_everything:
        raise PermissionDenied()


def _enqueue_scan(file_object_id: str) -> None:
    """Si el broker no responde, la evidencia queda ``PENDING`` y la retoma
    ``requeue_pending_scans``."""
    from apps.documents.tasks import log_eager_failure
    from apps.filings.tasks import scan_filing_evidence

    try:
        result = scan_filing_evidence.delay(file_object_id)
    except OperationalError:
        logger.warning("No se pudo encolar el análisis de la evidencia %s", file_object_id)
        return
    log_eager_failure(result, f"Análisis de la evidencia {file_object_id}")


def _attach(response_id: uuid.UUID, file_object_values: dict[str, object]) -> FileObject:
    with transaction.atomic():
        locked = FilingResponse.objects.select_for_update().get(pk=response_id)
        if locked.evidence_file_object_id is not None:
            raise EvidenceAlreadyAttached()
        file_object = FileObject.objects.create(**file_object_values)
        locked.evidence_file_object = file_object
        locked.save(update_fields=["evidence_file_object"])
        transaction.on_commit(partial(_enqueue_scan, str(file_object.pk)))
    return file_object


def attach_evidence(
    actor: User,
    response: FilingResponse,
    *,
    stream: BinaryIO,
    filename: str,
    declared_mime_type: str | None,
) -> FileObject:
    """Valida, guarda y adjunta la evidencia. Errores: ``400`` (vacío o sin nombre),
    ``422 UNSUPPORTED_FILE_TYPE``, ``422 FILE_TOO_LARGE``, ``409
    EVIDENCE_ALREADY_ATTACHED`` y ``503 SERVICE_UNAVAILABLE``."""
    ensure_can_attach(actor, response)
    if response.evidence_file_object_id is not None:
        raise EvidenceAlreadyAttached()
    inspected = inspect_upload(
        stream,
        filename=filename,
        declared_mime_type=declared_mime_type,
        allowed_mime_types=EVIDENCE_MIME_TYPES,
        max_size_bytes=EVIDENCE_MAX_BYTES,
    )
    storage = get_storage()
    key = new_evidence_key(response.filing.application_id)
    try:
        storage.put(key, stream, content_type=inspected.mime_type)
    except StorageUnavailable as exc:
        logger.warning("Almacenamiento no disponible al cargar la evidencia de %s", response.pk)
        raise UploadUnavailable() from exc
    try:
        file_object = _attach(
            response.pk,
            {
                "storage_provider": storage.provider,
                "bucket_name": storage.bucket,
                "object_key": key,
                "original_filename": inspected.filename,
                "detected_mime_type": inspected.mime_type,
                "size_bytes": inspected.size_bytes,
                "sha256": inspected.sha256,
                "encryption_key_version": storage.encryption_key_version,
            },
        )
    except BaseException:
        try:
            storage.delete(key)
        except StorageUnavailable:
            logger.warning("No se pudo borrar la evidencia huérfana de %s", response.pk)
        raise
    logger.info("Evidencia adjunta a la respuesta %s por %s", response.pk, actor.pk)
    return file_object


def scan_evidence(file_object_id: uuid.UUID) -> str | None:
    """Analiza una evidencia pendiente. Devuelve el estado resultante, o ``None`` si el
    archivo no es la evidencia de una respuesta. Idempotente."""
    file_object = FileObject.objects.filter(
        pk=file_object_id, filing_responses__isnull=False
    ).first()
    if file_object is None:
        logger.warning(
            "Análisis pedido para un archivo que no es una evidencia: %s", file_object_id
        )
        return None
    if file_object.scan_status != ScanStatus.PENDING:
        return file_object.scan_status
    result = inspect_file_object(file_object)
    with transaction.atomic():
        locked = FileObject.objects.select_for_update().get(pk=file_object_id)
        if locked.scan_status != ScanStatus.PENDING:
            return locked.scan_status
        locked.scan_status = result.status
        locked.scanned_at = timezone.now()
        locked.save(update_fields=["scan_status", "scanned_at"])
    if result.status != ScanStatus.CLEAN:
        logger.warning("Evidencia %s rechazada por el análisis (%s)", file_object_id, result.status)
    return result.status


def evidence_download(response: FilingResponse, *, requested_by: str) -> DownloadLink:
    file_object = response.evidence_file_object
    assert file_object is not None
    return file_object_link(
        file_object,
        filename=file_object.original_filename,
        requested_by=requested_by,
        description=f"la evidencia de la respuesta {response.pk}",
    )
