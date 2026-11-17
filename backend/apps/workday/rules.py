"""Reglas fijas de "Mi día" (RF-21, RF-22, API §15.1): segmentos de atención y siguiente
acción por estado.

Son configuración en el código, como las pestañas del listado: los estados son código
(``ApplicationStatus``) y las etiquetas viven aquí, en una sola constante cada una. Las
pruebas verifican que cada estado no terminal tenga siguiente acción y que cada segmento
tenga su regla.
"""

from datetime import datetime, time

from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.applications.models import TERMINAL_APPLICATION_STATUSES
from apps.applications.services import buyer_inactive_condition
from apps.catalogs.workflow import ApplicationStatus as S
from apps.documents.models import ApplicationDocumentSlot, SlotStatus
from apps.tasks.models import Task, TaskStatus

# Solo las solicitudes en curso entran a "Mi día".
WORKDAY_STATUSES: tuple[str, ...] = tuple(
    status for status in S.values if status not in TERMINAL_APPLICATION_STATUSES
)


class AttentionSegment(models.TextChoices):
    """Segmentos de atención, en el orden de ``/workday/summary``. No son excluyentes."""

    REVIEW_DOCUMENTS = "REVIEW_DOCUMENTS", "Documentos por revisar"
    READY_TO_FILE = "READY_TO_FILE", "Listas para radicar"
    FILED = "FILED", "Radicadas"
    IN_ANALYSIS = "IN_ANALYSIS", "En análisis"
    OBSERVED = "OBSERVED", "Observadas por el banco"
    BUYER_INACTIVE = "BUYER_INACTIVE", "Comprador sin actividad"
    TASKS_DUE = "TASKS_DUE", "Con tareas vencidas o de hoy"


class NextAction(models.TextChoices):
    COMPLETE_DRAFT = "COMPLETE_DRAFT", "Completar el borrador"
    FOLLOW_UP_BUYER_DATA = "FOLLOW_UP_BUYER_DATA", "Hacer seguimiento a los datos del comprador"
    FOLLOW_UP_DOCUMENTS = "FOLLOW_UP_DOCUMENTS", "Hacer seguimiento a los documentos"
    REVIEW_DOCUMENTS = "REVIEW_DOCUMENTS", "Revisar documentos"
    FILE_WITH_BANK = "FILE_WITH_BANK", "Radicar en el banco"
    WAIT_BANK_RESPONSE = "WAIT_BANK_RESPONSE", "Esperar respuesta del banco"
    RESOLVE_OBSERVATIONS = "RESOLVE_OBSERVATIONS", "Resolver las observaciones del banco"
    START_LEGALIZATION = "START_LEGALIZATION", "Iniciar la legalización"
    FOLLOW_UP_LEGALIZATION = "FOLLOW_UP_LEGALIZATION", "Hacer seguimiento a la legalización"


# Estado no terminal → siguiente acción del asesor.
NEXT_ACTIONS: dict[str, NextAction] = {
    S.DRAFT: NextAction.COMPLETE_DRAFT,
    S.WAITING_BUYER_DATA: NextAction.FOLLOW_UP_BUYER_DATA,
    S.WAITING_DOCUMENTS: NextAction.FOLLOW_UP_DOCUMENTS,
    S.DOCUMENTS_REVIEW: NextAction.REVIEW_DOCUMENTS,
    S.READY_TO_FILE: NextAction.FILE_WITH_BANK,
    S.FILED: NextAction.WAIT_BANK_RESPONSE,
    S.FILING_VALIDATION: NextAction.WAIT_BANK_RESPONSE,
    S.CREDIT_ANALYSIS: NextAction.WAIT_BANK_RESPONSE,
    S.BANK_OBSERVATION: NextAction.RESOLVE_OBSERVATIONS,
    S.APPROVED: NextAction.START_LEGALIZATION,
    S.LEGALIZATION: NextAction.FOLLOW_UP_LEGALIZATION,
}


def end_of_today() -> datetime:
    """Último instante de hoy en la zona del proyecto (``TIME_ZONE``, Bogotá)."""
    today = timezone.localdate()
    return timezone.make_aware(datetime.combine(today, time.max))


def segment_conditions(now: datetime) -> dict[str, Q]:
    """La regla de cada segmento sobre ``credit_applications``, por código. Todas son
    condiciones de base de datos: las filas, el filtro ``attention`` y los conteos del
    resumen usan exactamente las mismas."""
    uploaded_slots = ApplicationDocumentSlot.objects.filter(
        application=OuterRef("pk"), retired_at__isnull=True, status=SlotStatus.UPLOADED
    )
    due_tasks = Task.objects.filter(
        application=OuterRef("pk"), status=TaskStatus.PENDING, due_at__lte=end_of_today()
    )
    return {
        AttentionSegment.REVIEW_DOCUMENTS: Q(Exists(uploaded_slots)),
        AttentionSegment.READY_TO_FILE: Q(status=S.READY_TO_FILE),
        AttentionSegment.FILED: Q(status__in=(S.FILED, S.FILING_VALIDATION)),
        AttentionSegment.IN_ANALYSIS: Q(status=S.CREDIT_ANALYSIS),
        AttentionSegment.OBSERVED: Q(status=S.BANK_OBSERVATION),
        AttentionSegment.BUYER_INACTIVE: buyer_inactive_condition(now),
        AttentionSegment.TASKS_DUE: Q(Exists(due_tasks)),
    }


def attention_field(code: str) -> str:
    """Nombre de la anotación booleana de un segmento en el queryset de "Mi día"."""
    return f"attention_{code.lower()}"
