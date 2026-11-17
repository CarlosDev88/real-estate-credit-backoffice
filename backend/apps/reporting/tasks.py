"""Tareas de Celery de los reportes. Reciben ids, nunca datos, y son idempotentes."""

import logging
import uuid

from celery import Task, shared_task

from apps.documents.exceptions import StorageUnavailable
from apps.documents.tasks import scan_retry_delay
from apps.reporting.export_jobs import build_export

logger = logging.getLogger(__name__)

# Reintentos como el paquete documental: 30 s, 1, 2, 4 y 8 min (≈ 15 min).
EXPORT_MAX_RETRIES = 5


@shared_task(bind=True, max_retries=EXPORT_MAX_RETRIES, acks_late=True)
def build_report_export(self: Task, job_id: str) -> str | None:
    """Arma el CSV de una exportación pedida. Si el almacenamiento falla, el trabajo
    vuelve a ``PENDING`` y se reintenta con espera creciente; en el último intento queda
    ``FAILED`` con ``STORAGE_UNAVAILABLE``. Un ``FAILED`` no se reintenta: se pide otra."""
    retries = self.request.retries
    try:
        return build_export(uuid.UUID(job_id), last_attempt=retries >= EXPORT_MAX_RETRIES)
    except StorageUnavailable as exc:
        logger.warning("Exportación %s fallida (%s): se reintenta", job_id, exc)
        raise self.retry(exc=exc, countdown=scan_retry_delay(retries)) from exc
