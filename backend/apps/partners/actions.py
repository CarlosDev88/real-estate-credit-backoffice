"""Tipo y motivo de cada acción disponible del proyecto.

Misma forma que las acciones de la solicitud (``apps.applications.actions``) y de la
oportunidad (``apps.crm.actions``):

- ``primary``: avanzar hacia la publicación (enviar a validación o aprobar).
- ``secondary``: devolver a borrador (``REJECT``).
- ``destructive``: archivar (``ARCHIVED``).

``reason_required``: devolver a borrador y archivar exigen ``reason`` (texto libre) en
``POST /projects/{id}/reject`` y ``POST /projects/{id}/archive``.

La lista sale en ese orden de grupos; dentro de cada grupo se conserva el orden de
``available_transitions`` (por código).
"""

from collections.abc import Iterable

from apps.catalogs.models import WorkflowTransition
from apps.catalogs.workflow import ActionKind, ProjectStatus

# Tipo según el estado destino. Cubre todos los estados: una prueba lo exige.
ACTION_KIND_BY_TARGET_STATUS: dict[str, ActionKind] = {
    ProjectStatus.DRAFT: ActionKind.SECONDARY,
    ProjectStatus.PENDING_REVIEW: ActionKind.PRIMARY,
    ProjectStatus.ACTIVE: ActionKind.PRIMARY,
    ProjectStatus.ARCHIVED: ActionKind.DESTRUCTIVE,
}

# Destinos cuyo endpoint exige `reason`: `/reject` (vuelve a `DRAFT`) y `/archive`.
REASON_REQUIRED_STATUSES: tuple[str, ...] = (ProjectStatus.DRAFT, ProjectStatus.ARCHIVED)

_KIND_RANK = {ActionKind.PRIMARY: 0, ActionKind.SECONDARY: 1, ActionKind.DESTRUCTIVE: 2}


def action_kind(transition: WorkflowTransition) -> ActionKind:
    return ACTION_KIND_BY_TARGET_STATUS[transition.to_status]


def reason_required(transition: WorkflowTransition) -> bool:
    return transition.to_status in REASON_REQUIRED_STATUSES


def sort_by_kind(transitions: Iterable[WorkflowTransition]) -> list[WorkflowTransition]:
    """Principales, secundarias y destructivas; ``sorted`` es estable dentro de cada grupo."""
    return sorted(transitions, key=lambda transition: _KIND_RANK[action_kind(transition)])
