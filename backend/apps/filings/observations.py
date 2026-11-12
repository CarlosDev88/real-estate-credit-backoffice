"""Observaciones abiertas del banco sobre los documentos de una solicitud.

Las usan la carga del comprador (``documents.uploads.slot_has_open_observation``) y la
guarda `APPLICATION_READY_TO_REFILE` (``applications.services``). Solo importa modelos:
los servicios de ``applications`` y ``documents`` la importan sin ciclos.
"""

import uuid
from typing import Any

from django.db.models import QuerySet

from apps.filings.models import FilingResponseObservation


def open_observations(application_id: uuid.UUID) -> QuerySet[FilingResponseObservation]:
    """Observaciones sin resolver de la solicitud, en el orden en que se registraron."""
    return FilingResponseObservation.objects.filter(
        document_slot__application_id=application_id, resolved_at__isnull=True
    ).order_by("created_at", "id")


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
