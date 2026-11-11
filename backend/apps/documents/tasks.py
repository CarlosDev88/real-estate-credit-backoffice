"""Tareas de Celery del expediente documental. Reciben ids, nunca archivos ni datos
personales, y son idempotentes."""

import logging
import uuid

from celery import Task, shared_task
from celery.result import AsyncResult, EagerResult

from apps.documents.exceptions import ScannerUnavailable, StorageUnavailable
from apps.documents.models import ScanStatus
from apps.documents.packages import build_package
from apps.documents.scans import scan_document_file

logger = logging.getLogger(__name__)


def log_eager_failure(result: AsyncResult, description: str) -> None:
    """En modo inmediato (``CELERY_TASK_ALWAYS_EAGER``) la tarea ya corrió dentro de la
    petición. Si falló, se registra con su traza y la petición sigue: el archivo o el
    paquete quedan en el estado en que los dejó la tarea."""
    if not isinstance(result, EagerResult) or not result.failed():
        return
    try:
        result.maybe_throw()
    except Exception:
        logger.exception("%s falló en modo inmediato", description)


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


# Reintentos del paquete: 30 s, 1, 2, 4 y 8 min (≈ 15 min). Alguien espera el ZIP.
PACKAGE_MAX_RETRIES = 5


@shared_task(bind=True, max_retries=PACKAGE_MAX_RETRIES, acks_late=True)
def build_document_package(self: Task, job_id: str) -> str | None:
    """Arma el ZIP de un paquete pedido. Si el almacenamiento falla, el trabajo vuelve a
    ``PENDING`` y se reintenta con espera creciente; en el último intento queda
    ``FAILED`` con ``STORAGE_UNAVAILABLE``. Un ``FAILED`` no se reintenta: se pide otro."""
    retries = self.request.retries
    try:
        return build_package(uuid.UUID(job_id), last_attempt=retries >= PACKAGE_MAX_RETRIES)
    except StorageUnavailable as exc:
        logger.warning("Paquete %s fallido (%s): se reintenta", job_id, exc)
        raise self.retry(exc=exc, countdown=scan_retry_delay(retries)) from exc
