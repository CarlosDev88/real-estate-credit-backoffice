"""Análisis de una versión cargada y su efecto en el expediente (decisión 3).

- ``CLEAN``: la versión pasa de ``UPLOADED`` a ``IN_REVIEW`` y espera al asesor.
- ``INFECTED``: lo dice el antivirus.
- ``INVALID``: el objeto guardado no coincide con la huella registrada al cargarlo.
- En los dos últimos casos la versión queda ``REJECTED`` (sin fila en
  ``document_reviews``) y, si sigue siendo la vigente, el slot también. El comprador
  ve un mensaje fijo.

Idempotente: si el archivo ya no está ``PENDING``, no hace nada. Si el almacenamiento
o el antivirus no responden, lanza ``StorageUnavailable`` o ``ScannerUnavailable`` y
el archivo sigue ``PENDING``: la tarea decide si reintenta.
"""

import hashlib
import io
import logging
import uuid

from django.db import transaction
from django.utils import timezone

from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    FileObject,
    ScanStatus,
    SlotStatus,
)
from apps.documents.scanning import ScanResult, get_scanner
from apps.documents.storage import get_storage

logger = logging.getLogger(__name__)

# Lo que ve el comprador cuando el análisis rechaza su archivo.
SECURITY_REJECTION_MESSAGE = "El archivo no pasó la validación de seguridad."


def inspect_file_object(file_object: FileObject) -> ScanResult:
    """Lee el objeto guardado, compara su huella y lo pasa por el antivirus. Lo usan
    también las evidencias de las respuestas del banco (paso 11)."""
    with get_storage().open(file_object.object_key) as stream:
        content = stream.read()
    if hashlib.sha256(content).hexdigest() != file_object.sha256:
        return ScanResult(ScanStatus.INVALID)
    return get_scanner().scan(io.BytesIO(content))


def _apply(file_object_id: uuid.UUID, result: ScanResult) -> str:
    with transaction.atomic():
        version = DocumentFile.objects.only("slot_id").get(file_object_id=file_object_id)
        # Orden de bloqueo: slot y después sus filas (decisión 22).
        slot = ApplicationDocumentSlot.objects.select_for_update().get(pk=version.slot_id)
        file_object = FileObject.objects.select_for_update().get(pk=file_object_id)
        if file_object.scan_status != ScanStatus.PENDING:
            return file_object.scan_status
        file_object.scan_status = result.status
        file_object.scanned_at = timezone.now()
        file_object.save(update_fields=["scan_status", "scanned_at"])

        version = DocumentFile.objects.get(pk=version.pk)
        if result.status == ScanStatus.CLEAN:
            if version.status == DocumentFileStatus.UPLOADED:
                version.status = DocumentFileStatus.IN_REVIEW
                version.save(update_fields=["status"])
        else:
            version.status = DocumentFileStatus.REJECTED
            version.save(update_fields=["status"])
            if slot.current_file_id == version.pk:
                slot.status = SlotStatus.REJECTED
                slot.save(update_fields=["status", "updated_at"])
        # Import local para no crear un ciclo con `apps.applications.services`.
        from apps.applications.services import schedule_completeness_refresh

        schedule_completeness_refresh(slot.application_id)
    if result.status == ScanStatus.INFECTED:
        logger.warning(
            "Archivo %s infectado (%s): versión %s rechazada",
            file_object_id,
            result.signature,
            version.pk,
        )
    elif result.status == ScanStatus.INVALID:
        logger.warning("Archivo %s no coincide con su huella: versión rechazada", file_object_id)
    return result.status


def scan_document_file(file_object_id: uuid.UUID) -> str | None:
    """Analiza el archivo de una versión pendiente. Devuelve el estado resultante, o
    ``None`` si no es el archivo de una versión."""
    file_object = FileObject.objects.filter(pk=file_object_id).first()
    if file_object is None or not DocumentFile.objects.filter(file_object=file_object).exists():
        logger.warning(
            "Análisis pedido para un archivo que no es de una versión: %s", file_object_id
        )
        return None
    if file_object.scan_status != ScanStatus.PENDING:
        return file_object.scan_status
    return _apply(file_object_id, inspect_file_object(file_object))
