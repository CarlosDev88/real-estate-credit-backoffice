"""Tareas de Celery del expediente documental. Reciben ids, nunca archivos ni datos
personales, y son idempotentes."""

import logging
import uuid

from celery import Task, shared_task

from apps.documents.exceptions import ScannerUnavailable, StorageUnavailable
from apps.documents.models import ScanStatus
from apps.documents.scans import scan_document_file

logger = logging.getLogger(__name__)

# Reintentos del análisis: 30 s, 1, 2, 4 y 8 min, y después cada 15 min (≈ 1 h 15 min).
SCAN_MAX_RETRIES = 8
SCAN_BASE_DELAY_SECONDS = 30
SCAN_MAX_DELAY_SECONDS = 15 * 60


def scan_retry_delay(retries: int) -> int:
    return int(min(SCAN_BASE_DELAY_SECONDS * 2**retries, SCAN_MAX_DELAY_SECONDS))


@shared_task(bind=True, max_retries=SCAN_MAX_RETRIES, acks_late=True)
def scan_file_object(self: Task, file_object_id: str) -> str | None:
    """Analiza una versión cargada. Si el almacenamiento o el antivirus fallan, reintenta
    con espera creciente; al agotar los reintentos el archivo sigue ``PENDING`` para
    ``requeue_pending_scans``. Nunca lo marca ``CLEAN`` sin un análisis real."""
    try:
        return scan_document_file(uuid.UUID(file_object_id))
    except (ScannerUnavailable, StorageUnavailable) as exc:
        retries = self.request.retries
        if retries >= SCAN_MAX_RETRIES:
            logger.error(
                "Análisis del archivo %s sin completar tras %s reintentos: queda pendiente",
                file_object_id,
                retries,
            )
            return ScanStatus.PENDING
        logger.warning("Análisis del archivo %s fallido (%s): se reintenta", file_object_id, exc)
        raise self.retry(exc=exc, countdown=scan_retry_delay(retries)) from exc
