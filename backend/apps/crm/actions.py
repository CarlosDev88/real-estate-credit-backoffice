"""Tipo y motivo de cada acción disponible de la oportunidad.

Misma forma que las acciones de la solicitud (``apps.applications.actions``):

- ``primary``: la conversión (``CONVERTED``, al crear la solicitud).
- ``destructive``: perder (``LOST``) o cancelar (``CANCELLED``).
- ``secondary``: el resto (asignar, contactar, iniciar gestión).

``reason_required``: solo ``LOST`` exige ``reason_code`` (catálogo
``opportunity_lost_reason``).

La lista sale en ese orden de grupos; dentro de cada grupo se conserva el orden de
``available_transitions`` (por código).
"""

from collections.abc import Iterable

from apps.catalogs.models import WorkflowTransition
from apps.catalogs.workflow import ActionKind, OpportunityStatus

# Tipo según el estado destino. Cubre todos los estados: una prueba lo exige.
ACTION_KIND_BY_TARGET_STATUS: dict[str, ActionKind] = {
    OpportunityStatus.NEW: ActionKind.SECONDARY,
    OpportunityStatus.ASSIGNED: ActionKind.SECONDARY,
    OpportunityStatus.CONTACTED: ActionKind.SECONDARY,
    OpportunityStatus.IN_PROGRESS: ActionKind.SECONDARY,
    OpportunityStatus.CONVERTED: ActionKind.PRIMARY,
    OpportunityStatus.LOST: ActionKind.DESTRUCTIVE,
    OpportunityStatus.CANCELLED: ActionKind.DESTRUCTIVE,
}

# Destinos que exigen `reason_code` en `POST /opportunities/{id}/transitions`.
REASON_REQUIRED_STATUSES: tuple[str, ...] = (OpportunityStatus.LOST,)

_KIND_RANK = {ActionKind.PRIMARY: 0, ActionKind.SECONDARY: 1, ActionKind.DESTRUCTIVE: 2}


def action_kind(transition: WorkflowTransition) -> ActionKind:
    return ACTION_KIND_BY_TARGET_STATUS[transition.to_status]


def reason_required(transition: WorkflowTransition) -> bool:
    return transition.to_status in REASON_REQUIRED_STATUSES


def sort_by_kind(transitions: Iterable[WorkflowTransition]) -> list[WorkflowTransition]:
    """Principales, secundarias y destructivas; ``sorted`` es estable dentro de cada grupo."""
    return sorted(transitions, key=lambda transition: _KIND_RANK[action_kind(transition)])
