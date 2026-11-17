"""Tareas manuales (RF-20, API §15.2): alcance, creación, edición, cierre y fechas.

- **Alcance:** el administrador ve todas. El asesor ve las asignadas a él y las de sus
  solicitudes (``assigned_advisor``) u oportunidades (asignadas o capturadas por él,
  como en CRM). El broker y la constructora no tienen permiso.
- **Responsable:** un usuario activo con rol `ADMIN` o `ADVISOR` (o un superusuario).
- **Estados:** solo una tarea `PENDING` se edita, se completa o se cancela; si no,
  ``409 TASK_NOT_PENDING``.
- **Fechas:** "vencida", "de hoy" y "próxima" se miden con la fecha de Bogotá
  (``TIME_ZONE``) y solo aplican a tareas `PENDING` con ``due_at``.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.applications.exceptions import ApplicationClosed
from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to, resolve_visible_opportunity
from apps.catalogs.models import CatalogItem
from apps.crm.models import Opportunity
from apps.crm.services import get_scope
from apps.identity.models import RoleCode, User
from apps.identity.services import get_access_profile
from apps.tasks.exceptions import TaskNotPending
from apps.tasks.models import PRIORITY_CATALOG, Task, TaskSource, TaskStatus
from apps.tasks.signals import task_cancelled, task_completed, task_created

DEFAULT_PRIORITY = "MEDIUM"
ASSIGNABLE_ROLES = (RoleCode.ADMIN, RoleCode.ADVISOR)

# Orden de la lista: por fecha, las que no tienen al final; después, por creación.
LIST_ORDERING = (F("due_at").asc(nulls_last=True), "created_at", "id")

# Campos que admite ``PATCH /tasks/{id}``.
EDITABLE_FIELDS = ("title", "description", "assigned_to", "due_at", "priority_item")


class DueWindow:
    """Valores del filtro ``due``."""

    OVERDUE = "overdue"
    TODAY = "today"
    UPCOMING = "upcoming"

    values = (OVERDUE, TODAY, UPCOMING)


# --- Fechas -----------------------------------------------------------------------------


def start_of_today() -> datetime:
    """Primer instante de hoy en la zona del proyecto (Bogotá)."""
    return timezone.make_aware(datetime.combine(timezone.localdate(), time.min))


def due_condition(window: str) -> Q:
    """Tareas `PENDING` vencidas (antes de hoy), de hoy o próximas (después de hoy)."""
    start = start_of_today()
    end = start + timedelta(days=1)
    by_window = {
        DueWindow.OVERDUE: Q(due_at__lt=start),
        DueWindow.TODAY: Q(due_at__gte=start, due_at__lt=end),
        DueWindow.UPCOMING: Q(due_at__gte=end),
    }
    return Q(status=TaskStatus.PENDING) & by_window[window]


def is_overdue(task: Task) -> bool:
    """La misma regla que ``due=overdue``: pendiente y con fecha anterior a hoy."""
    return (
        task.status == TaskStatus.PENDING
        and task.due_at is not None
        and task.due_at < start_of_today()
    )


# --- Alcance ----------------------------------------------------------------------------


def tasks_queryset() -> QuerySet[Task]:
    """Tareas con lo que muestra la respuesta, en una sola consulta."""
    return Task.objects.select_related(
        "assigned_to",
        "created_by",
        "priority_item",
        "application__opportunity__client",
        "opportunity__client",
    )


def scope_condition(user: User) -> Q | None:
    """Filtro de tareas visibles, o ``None`` si el usuario ve todas."""
    scope = get_scope(user)
    if scope.sees_everything:
        return None
    condition = Q(assigned_to=user)
    if scope.is_advisor:
        condition |= (
            Q(application__assigned_advisor=user)
            | Q(opportunity__assigned_advisor=user)
            | Q(opportunity__origin_user=user)
        )
    return condition


def tasks_visible_to(user: User) -> QuerySet[Task]:
    tasks = tasks_queryset()
    condition = scope_condition(user)
    return tasks if condition is None else tasks.filter(condition)


def sees_everything(user: User) -> bool:
    return get_scope(user).sees_everything


# --- Referencias del cuerpo -------------------------------------------------------------


@dataclass(frozen=True)
class TaskParent:
    application: CreditApplication | None = None
    opportunity: Opportunity | None = None


def resolve_parent(
    user: User, *, application_id: uuid.UUID | None, opportunity_id: uuid.UUID | None
) -> TaskParent:
    """Exactamente un padre, visible para ``user``. Una solicitud terminada responde
    ``409 APPLICATION_CLOSED``."""
    if (application_id is None) == (opportunity_id is None):
        raise ValidationError(
            {"non_field_errors": ["Indica application_id u opportunity_id (solo uno)."]}
        )
    if opportunity_id is not None:
        return TaskParent(opportunity=resolve_visible_opportunity(user, opportunity_id))
    assert application_id is not None
    application = applications_visible_to(user).filter(pk=application_id).first()
    if application is None:
        raise ValidationError({"application_id": ["La solicitud no existe."]})
    if application.is_terminal:
        raise ApplicationClosed()
    return TaskParent(application=application)


def ensure_assignable(user: User) -> None:
    """El responsable es un usuario activo con rol `ADMIN` o `ADVISOR`."""
    roles = set(get_access_profile(user).roles)
    if not user.can_authenticate or not (user.is_superuser or roles & set(ASSIGNABLE_ROLES)):
        raise ValidationError(
            {
                "assigned_to_id": [
                    "El responsable debe ser un usuario activo administrador o asesor."
                ]
            }
        )


def resolve_assignee(user_id: uuid.UUID) -> User:
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if user is None:
        raise ValidationError({"assigned_to_id": ["El usuario no existe."]})
    ensure_assignable(user)
    return user


def default_priority() -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=PRIORITY_CATALOG, code=DEFAULT_PRIORITY)


# --- Escrituras -------------------------------------------------------------------------


def create_task(
    actor: User,
    *,
    parent: TaskParent,
    title: str,
    description: str = "",
    assignee: User | None = None,
    due_at: datetime | None = None,
    priority: CatalogItem | None = None,
) -> Task:
    """Crea una tarea manual `PENDING`. El responsable por omisión es el actor."""
    assignee = assignee or actor
    ensure_assignable(assignee)
    with transaction.atomic():
        task = Task.objects.create(
            application=parent.application,
            opportunity=parent.opportunity,
            assigned_to=assignee,
            created_by=actor,
            title=title,
            description=description,
            priority_item=priority or default_priority(),
            source=TaskSource.MANUAL,
            due_at=due_at,
        )
        transaction.on_commit(lambda: task_created.send(sender=Task, task=task, actor=actor))
    return task


def _lock_pending(task: Task) -> Task:
    locked = Task.objects.select_for_update().get(pk=task.pk)
    if locked.status != TaskStatus.PENDING:
        raise TaskNotPending()
    return locked


def update_task(actor: User, task: Task, changes: dict[str, Any]) -> Task:
    """Cambia título, descripción, responsable, fecha o prioridad de una tarea `PENDING`."""
    if "assigned_to" in changes:
        ensure_assignable(changes["assigned_to"])
    with transaction.atomic():
        locked = _lock_pending(task)
        fields = [field for field in EDITABLE_FIELDS if field in changes]
        for field in fields:
            setattr(locked, field, changes[field])
        if fields:
            locked.save(update_fields=[*fields, "updated_at"])
    return locked


def complete_task(actor: User, task: Task) -> Task:
    with transaction.atomic():
        locked = _lock_pending(task)
        locked.status = TaskStatus.COMPLETED
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "completed_at", "updated_at"])
        transaction.on_commit(lambda: task_completed.send(sender=Task, task=locked, actor=actor))
    return locked


def cancel_task(actor: User, task: Task, *, reason: str) -> Task:
    with transaction.atomic():
        locked = _lock_pending(task)
        locked.status = TaskStatus.CANCELLED
        locked.cancelled_at = timezone.now()
        locked.cancel_reason = reason
        locked.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
        transaction.on_commit(
            lambda: task_cancelled.send(sender=Task, task=locked, reason=reason, actor=actor)
        )
    return locked
