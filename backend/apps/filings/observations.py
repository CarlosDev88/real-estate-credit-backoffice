"""Observaciones del banco sobre los documentos de una solicitud.

Las usan la carga del comprador (``documents.uploads.slot_has_open_observation``), la
aprobación del asesor (``documents.reviews``) y la guarda `APPLICATION_READY_TO_REFILE`
(``applications.services``). Solo importa modelos: esos módulos la importan sin ciclos.

Una observación queda abierta hasta que el asesor **aprueba una versión nueva** del slot,
cargada después de la observación. Aprobar otra vez la versión observada no la resuelve:
responde ``409 DOCUMENT_OBSERVED``.
"""

import uuid
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.documents.models import ApplicationDocumentSlot, DocumentFile
from apps.filings.exceptions import DocumentObserved
from apps.filings.models import FilingResponseObservation


def open_observations(application_id: uuid.UUID) -> QuerySet[FilingResponseObservation]:
    """Observaciones sin resolver de la solicitud, en el orden en que se registraron."""
    return FilingResponseObservation.objects.filter(
        document_slot__application_id=application_id, resolved_at__isnull=True
    ).order_by("created_at", "id")


def has_open_observation(slot: ApplicationDocumentSlot) -> bool:
    return FilingResponseObservation.objects.filter(
        document_slot=slot, resolved_at__isnull=True
    ).exists()


def open_observation_problems(application_id: uuid.UUID) -> list[dict[str, Any]]:
    """Un ``BANK_OBSERVATION_OPEN`` por cada slot con una observación sin resolver, para
    los ``details`` de ``APPLICATION_NOT_READY``."""
    slot_ids = list(
        dict.fromkeys(open_observations(application_id).values_list("document_slot_id", flat=True))
    )
    return [
        {
            "field": "documents",
            "code": "BANK_OBSERVATION_OPEN",
            "message": "El banco observó este documento y la observación sigue abierta: "
            "aprueba una versión nueva.",
            "resource_id": str(slot_id),
        }
        for slot_id in slot_ids
    ]


def resolve_on_approval(slot: ApplicationDocumentSlot, version: DocumentFile) -> int:
    """Al aprobar ``version``, resuelve las observaciones abiertas del slot anteriores a
    ella. Si alguna es posterior (se está aprobando la versión observada), ``409
    DOCUMENT_OBSERVED``. Devuelve cuántas resolvió. Va dentro de la transacción de la
    revisión, con el slot bloqueado."""
    pending = FilingResponseObservation.objects.select_for_update().filter(
        document_slot=slot, resolved_at__isnull=True
    )
    if pending.filter(created_at__gte=version.created_at).exists():
        raise DocumentObserved()
    return pending.update(resolved_by_file=version, resolved_at=timezone.now())
