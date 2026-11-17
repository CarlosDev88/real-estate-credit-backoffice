"""Tipo de cada acción disponible de la solicitud: principal, secundaria o destructiva.

El front usa la primera acción principal como botón principal y pide confirmación en
las destructivas. La regla es de negocio, así que vive aquí y no en el front:

- ``destructive``: termina la solicitud sin crédito (``CANCELLED`` o ``WITHDRAWN``).
- ``secondary``: la cierra por fuera del banco (``OWN_FUNDS`` o
  ``EXTERNAL_CREDIT_APPROVED``) o retrocede en el camino principal
  (``BACKWARD_TRANSITION_CODES``).
- ``primary``: avanza en el camino principal.

La lista disponible sale en ese orden de grupos; dentro de cada grupo se conserva el
orden de ``available_transitions`` (por código).
"""

from collections.abc import Iterable

from django.db import models

from apps.catalogs.models import WorkflowTransition
from apps.catalogs.workflow import ApplicationStatus


class ActionKind(models.TextChoices):
    PRIMARY = "primary", "Principal"
    SECONDARY = "secondary", "Secundaria"
    DESTRUCTIVE = "destructive", "Destructiva"


# Tipo según el estado destino. Cubre todos los estados: una prueba lo exige.
ACTION_KIND_BY_TARGET_STATUS: dict[str, ActionKind] = {
    ApplicationStatus.DRAFT: ActionKind.PRIMARY,
    ApplicationStatus.WAITING_BUYER_DATA: ActionKind.PRIMARY,
    ApplicationStatus.WAITING_DOCUMENTS: ActionKind.PRIMARY,
    ApplicationStatus.DOCUMENTS_REVIEW: ActionKind.PRIMARY,
    ApplicationStatus.READY_TO_FILE: ActionKind.PRIMARY,
    ApplicationStatus.FILED: ActionKind.PRIMARY,
    ApplicationStatus.FILING_VALIDATION: ActionKind.PRIMARY,
    ApplicationStatus.CREDIT_ANALYSIS: ActionKind.PRIMARY,
    ApplicationStatus.APPROVED: ActionKind.PRIMARY,
    ApplicationStatus.LEGALIZATION: ActionKind.PRIMARY,
    ApplicationStatus.DISBURSED: ActionKind.PRIMARY,
    ApplicationStatus.BANK_OBSERVATION: ActionKind.PRIMARY,
    ApplicationStatus.REJECTED: ActionKind.PRIMARY,
    ApplicationStatus.EXTERNAL_CREDIT_APPROVED: ActionKind.SECONDARY,
    ApplicationStatus.OWN_FUNDS: ActionKind.SECONDARY,
    ApplicationStatus.WITHDRAWN: ActionKind.DESTRUCTIVE,
    ApplicationStatus.CANCELLED: ActionKind.DESTRUCTIVE,
}

# Transiciones que retroceden en el camino principal: son secundarias aunque su
# destino sea un estado del camino principal.
BACKWARD_TRANSITION_CODES: frozenset[str] = frozenset({"RETURN_TO_DOCUMENTS", "REOPEN_REVIEW"})

_KIND_RANK = {ActionKind.PRIMARY: 0, ActionKind.SECONDARY: 1, ActionKind.DESTRUCTIVE: 2}


def action_kind(transition: WorkflowTransition) -> ActionKind:
    """Tipo de la acción. Las transiciones no inventan estados, así que el destino siempre
    está en ``ACTION_KIND_BY_TARGET_STATUS``."""
    if transition.code in BACKWARD_TRANSITION_CODES:
        return ActionKind.SECONDARY
    return ACTION_KIND_BY_TARGET_STATUS[transition.to_status]


def sort_by_kind(transitions: Iterable[WorkflowTransition]) -> list[WorkflowTransition]:
    """Principales, secundarias y destructivas; ``sorted`` es estable dentro de cada grupo."""
    return sorted(transitions, key=lambda transition: _KIND_RANK[action_kind(transition)])
