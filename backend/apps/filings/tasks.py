"""Tareas de Celery de la radicación. Reciben ids y son idempotentes."""

import logging
import uuid

from celery import Task, shared_task

from apps.documents.exceptions import ScannerUnavailable, StorageUnavailable
from apps.documents.models import ScanStatus
from apps.documents.tasks import SCAN_MAX_RETRIES, scan_retry_delay
from apps.filings.evidence import scan_evidence

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=SCAN_MAX_RETRIES, acks_late=True)
def scan_filing_evidence(self: Task, file_object_id: str) -> str | None:
    """Analiza la evidencia de una respuesta del banco, con los mismos reintentos que las
    versiones de los documentos. Al agotarlos sigue ``PENDING`` para
    ``requeue_pending_scans``; nunca se marca ``CLEAN`` sin un análisis real."""
    try:
        return scan_evidence(uuid.UUID(file_object_id))
    except (ScannerUnavailable, StorageUnavailable) as exc:
        retries = self.request.retries
        if retries >= SCAN_MAX_RETRIES:
            logger.error(
                "Análisis de la evidencia %s sin completar tras %s reintentos: queda pendiente",
                file_object_id,
                retries,
            )
            return ScanStatus.PENDING
        logger.warning(
            "Análisis de la evidencia %s fallido (%s): se reintenta", file_object_id, exc
        )
        raise self.retry(exc=exc, countdown=scan_retry_delay(retries)) from exc
