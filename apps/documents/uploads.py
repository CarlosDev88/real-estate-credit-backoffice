"""Carga de documentos por el comprador (decisiones 1, 4, 5, 11 y 22).

Solo el comprador carga. Cada carga es una versión nueva del slot: la anterior se
conserva con su estado, ``current_file`` pasa a la nueva y el slot queda ``UPLOADED``.
El análisis antivirus se encola al confirmar la transacción.

Qué se puede cargar:

- **Antes de `FILED`:** slots ``PENDING``, ``UPLOADED`` y ``REJECTED``. Sobre uno
  ``APPROVED`` o ``WAIVED``: ``409 DOCUMENT_LOCKED`` (el asesor primero rechaza la
  versión aprobada).
- **Después de `FILED`:** solo un slot ``REJECTED`` con observación abierta del banco.
  Un slot bloqueado (``locked_at``) sin observación: ``409 DOCUMENT_LOCKED``; cualquier
  otro: ``409 DOCUMENT_NOT_REJECTED``.
- **Solicitud terminada:** ``409 APPLICATION_CLOSED``.

El archivo se valida y se guarda en el almacenamiento antes de abrir la transacción,
para no retener los bloqueos durante la red. Si la transacción falla, el objeto se
borra.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from typing import Any, BinaryIO

from django.conf import settings
from django.db import transaction
from django.db.models import Max, QuerySet, Sum
from django.http import Http404
from kombu.exceptions import OperationalError

from apps.applications.exceptions import ApplicationClosed
from apps.applications.models import CreditApplication
from apps.documents.exceptions import (
    DocumentLocked,
    DocumentNotRejected,
    DocumentQuotaExceeded,
    StorageUnavailable,
    UploadUnavailable,
)
from apps.documents.file_validation import InspectedFile, inspect_upload
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    FileObject,
    SlotStatus,
)
from apps.documents.storage import get_storage, new_document_key
from apps.identity.models import BuyerSession
from config.exceptions import ApiError

logger = logging.getLogger(__name__)

# Estados del slot que admiten una carga antes de `FILED`.
UPLOADABLE_STATUSES = (SlotStatus.PENDING, SlotStatus.UPLOADED, SlotStatus.REJECTED)


def slot_has_open_observation(slot: ApplicationDocumentSlot) -> bool:
    """¿El banco observó este documento y la observación sigue abierta?

    Punto de enganche del paso 11 (``filing_response_observations``). Hasta entonces
    falla cerrado: después de `FILED` no se reemplaza nada.
    """
    return False


def upload_block(application: CreditApplication, slot: ApplicationDocumentSlot) -> ApiError | None:
    """El error que impediría cargar en el slot, o ``None`` si se puede.

    No mira los consentimientos ni la cuota: los primeros los exige la vista y la
    segunda depende del archivo.
    """
    if application.is_terminal:
        return ApplicationClosed()
    if application.is_editable:
        if slot.status in UPLOADABLE_STATUSES:
            return None
        return DocumentLocked()
    has_observation = slot_has_open_observation(slot)
    if has_observation and slot.status == SlotStatus.REJECTED:
        return None
    if slot.locked_at is not None and not has_observation:
        return DocumentLocked()
    return DocumentNotRejected()


def _ensure_can_upload(application: CreditApplication, slot: ApplicationDocumentSlot) -> None:
    error = upload_block(application, slot)
    if error is not None:
        raise error


def buyer_slots(session: BuyerSession) -> QuerySet[ApplicationDocumentSlot]:
    """Slots vigentes de la solicitud de la sesión. Los retirados no existen para el
    comprador (``404``)."""
    return ApplicationDocumentSlot.objects.filter(
        application_id=session.application_id, retired_at__isnull=True
    )


@dataclass(frozen=True)
class Upload:
    stream: BinaryIO
    filename: str
    declared_mime_type: str | None
    document_date: date | None = None


def _quota_detail(code: str, message: str) -> list[dict[str, Any]]:
    return [{"field": "file", "code": code, "message": message}]


def _ensure_quota(slot: ApplicationDocumentSlot, size_bytes: int) -> None:
    max_versions = settings.DOCUMENT_UPLOAD_MAX_VERSIONS_PER_SLOT
    if DocumentFile.objects.filter(slot=slot).count() >= max_versions:
        raise DocumentQuotaExceeded(
            details=_quota_detail(
                "VERSIONS_PER_SLOT",
                f"Este documento ya tiene {max_versions} versiones cargadas.",
            )
        )
    used = FileObject.objects.filter(document_file__slot__application_id=slot.application_id)
    total = used.aggregate(total=Sum("size_bytes"))["total"] or 0
    if total + size_bytes > settings.DOCUMENT_UPLOAD_QUOTA_BYTES:
        raise DocumentQuotaExceeded(
            details=_quota_detail(
                "APPLICATION_BYTES",
                "La solicitud alcanzó el espacio máximo para documentos.",
            )
        )


def expires_on(slot: ApplicationDocumentSlot, document_date: date | None) -> date | None:
    """Vencimiento de un documento del slot: ``document_date + validity_days``."""
    if document_date is None or slot.validity_days is None:
        return None
    return document_date + timedelta(days=slot.validity_days)


def _enqueue_scan(file_object_id: str) -> None:
    """Encola el análisis. Si el broker no responde, la carga ya quedó guardada: el
    archivo sigue ``PENDING`` y lo retoma ``requeue_pending_scans``."""
    from apps.documents.tasks import scan_file_object

    try:
        scan_file_object.delay(file_object_id)
    except OperationalError:
        logger.warning("No se pudo encolar el análisis del archivo %s", file_object_id)


def _save_version(
    session: BuyerSession,
    slot_id: Any,
    upload: Upload,
    inspected: InspectedFile,
    key: str,
) -> DocumentFile:
    storage = get_storage()
    with transaction.atomic():
        # Orden de bloqueo: solicitud y después slot (decisión 22).
        application = CreditApplication.objects.select_for_update().get(pk=session.application_id)
        slot = buyer_slots(session).select_for_update().filter(pk=slot_id).first()
        if slot is None:
            raise Http404
        _ensure_can_upload(application, slot)
        _ensure_quota(slot, inspected.size_bytes)

        latest = DocumentFile.objects.filter(slot=slot).aggregate(latest=Max("version_number"))
        file_object = FileObject.objects.create(
            storage_provider=storage.provider,
            bucket_name=storage.bucket,
            object_key=key,
            original_filename=inspected.filename,
            detected_mime_type=inspected.mime_type,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
            encryption_key_version=storage.encryption_key_version,
        )
        version = DocumentFile.objects.create(
            slot=slot,
            file_object=file_object,
            version_number=(latest["latest"] or 0) + 1,
            uploaded_by_buyer_session=session,
            client_filename=inspected.filename,
            document_date=upload.document_date,
            expires_at=expires_on(slot, upload.document_date),
        )
        slot.current_file = version
        slot.status = SlotStatus.UPLOADED
        slot.save(update_fields=["current_file", "status", "updated_at"])
        transaction.on_commit(partial(_enqueue_scan, str(file_object.pk)))
    return version


def upload_document(
    session: BuyerSession, slot: ApplicationDocumentSlot, upload: Upload
) -> DocumentFile:
    """Valida, guarda y registra una versión nueva del slot.

    Errores: ``400`` (archivo vacío o sin nombre), ``422 UNSUPPORTED_FILE_TYPE``,
    ``422 FILE_TOO_LARGE``, ``409 DOCUMENT_LOCKED``, ``409 DOCUMENT_NOT_REJECTED``,
    ``409 DOCUMENT_QUOTA_EXCEEDED``, ``409 APPLICATION_CLOSED`` y ``503
    SERVICE_UNAVAILABLE`` si el almacenamiento no responde.
    """
    # Comprobaciones baratas antes de leer el archivo; se repiten con los bloqueos.
    application = CreditApplication.objects.get(pk=session.application_id)
    _ensure_can_upload(application, slot)
    document_type = slot.document_type
    inspected = inspect_upload(
        upload.stream,
        filename=upload.filename,
        declared_mime_type=upload.declared_mime_type,
        allowed_mime_types=document_type.allowed_mime_types,
        max_size_bytes=document_type.max_size_bytes,
    )
    _ensure_quota(slot, inspected.size_bytes)

    storage = get_storage()
    key = new_document_key(application.pk)
    try:
        storage.put(key, upload.stream, content_type=inspected.mime_type)
    except StorageUnavailable as exc:
        logger.warning("Almacenamiento no disponible al cargar en el slot %s", slot.pk)
        raise UploadUnavailable() from exc

    try:
        version = _save_version(session, slot.pk, upload, inspected, key)
    except BaseException:
        try:
            storage.delete(key)
        except StorageUnavailable:
            logger.warning("No se pudo borrar un objeto huérfano del slot %s", slot.pk)
        raise

    logger.info(
        "Versión %s cargada en el slot %s por la sesión %s",
        version.version_number,
        slot.pk,
        session.pk,
    )
    return version
