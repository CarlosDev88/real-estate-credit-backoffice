"""Casos de uso del módulo crm: clientes, direcciones, oportunidades y asignaciones.

Alcance por rol (sección 8.6 de los requerimientos y RF-14):

- ``ADMIN``: todo.
- ``ADVISOR``: oportunidades asignadas a él o que él capturó, y sus clientes; también
  los participantes de las solicitudes que tiene asignadas, aunque se hayan retirado.
  La oportunidad que crea un asesor queda asignada a él (``create_opportunity``).
- ``INDEPENDENT_BROKER``: oportunidades que él capturó y clientes que creó. Solo ve
  datos de contacto y un resumen; nunca datos financieros ni documentos.
- ``CONSTRUCTION_PARTNER``: no usa estos endpoints en el MVP (sección 14 de la API).

Un recurso fuera del alcance responde 404, para no confirmar que existe.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogs.models import CatalogItem, WorkflowTransition
from apps.catalogs.services import available_transitions, resolve_transition
from apps.catalogs.workflow import FlowType, OpportunityStatus
from apps.crm.actions import sort_by_kind
from apps.crm.exceptions import (
    AdvisorNotEligible,
    DuplicateClientDocument,
    DuplicateOpportunity,
    OpportunityNotEditable,
)
from apps.crm.models import (
    OPEN_OPPORTUNITY_STATUSES,
    Client,
    ClientAddress,
    Opportunity,
    OpportunityAssignment,
)
from apps.crm.signals import (
    opportunity_assigned,
    opportunity_created,
    opportunity_status_changed,
)
from apps.identity.models import RoleCode, User
from apps.identity.services import get_access_profile
from apps.partners.models import Project
from apps.partners.services import ensure_project_accepts_opportunities, projects_visible_to

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Alcance
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CrmScope:
    sees_everything: bool
    is_advisor: bool
    is_broker: bool

    @property
    def is_restricted(self) -> bool:
        """El broker solo recibe datos de contacto y resumen."""
        return self.is_broker and not self.sees_everything and not self.is_advisor


def get_scope(user: User) -> CrmScope:
    roles = set(get_access_profile(user).roles)
    return CrmScope(
        sees_everything=user.is_superuser or RoleCode.ADMIN in roles,
        is_advisor=RoleCode.ADVISOR in roles,
        is_broker=RoleCode.INDEPENDENT_BROKER in roles,
    )


def _opportunity_scope_filter(user: User, scope: CrmScope) -> Q | None:
    """Filtro de oportunidades visibles, o ``None`` si el usuario ve todas."""
    if scope.sees_everything:
        return None
    condition = Q(pk__in=[])
    if scope.is_advisor:
        condition |= Q(assigned_advisor=user) | Q(origin_user=user)
    if scope.is_broker:
        condition |= Q(origin_user=user)
    return condition


def opportunities_visible_to(user: User) -> QuerySet[Opportunity]:
    opportunities = Opportunity.objects.select_related(
        "client",
        "project__partner",
        "origin_user",
        "assigned_advisor",
        "origin_item",
        "lost_reason_item",
    )
    condition = _opportunity_scope_filter(user, get_scope(user))
    return opportunities if condition is None else opportunities.filter(condition)


def clients_visible_to(user: User) -> QuerySet[Client]:
    clients = Client.objects.filter(deleted_at__isnull=True).select_related(
        "document_type_item", "origin_item", "created_by"
    )
    scope = get_scope(user)
    condition = _opportunity_scope_filter(user, scope)
    if condition is None:
        return clients
    if not (scope.is_advisor or scope.is_broker):
        return clients.none()
    related_opportunity = Opportunity.objects.filter(condition, client=OuterRef("pk"))
    visible = Q(created_by=user) | Q(Exists(related_opportunity))
    if scope.is_advisor:
        visible |= Q(Exists(_assigned_participations(user)))
    return clients.filter(visible)


def application_scope_condition(user: User, scope: CrmScope, prefix: str = "") -> Q | None:
    """Filtro de las solicitudes visibles para ``user``, o ``None`` si ve todas.

    Es la regla de ``applications.services.applications_visible_to``: vive aquí para que
    el conteo de solicitudes del cliente la use sin importar ``applications``.
    ``prefix`` apunta a la solicitud desde otro modelo (``"application__"``).
    """
    if scope.sees_everything:
        return None
    condition = Q(**{f"{prefix}pk__in": []})
    if scope.is_advisor:
        condition |= Q(**{f"{prefix}assigned_advisor": user})
    if scope.is_broker:
        condition |= Q(**{f"{prefix}opportunity__origin_user": user})
    return condition


def with_applications_count(clients: QuerySet[Client], user: User) -> QuerySet[Client]:
    """Anota ``applications_count``: solicitudes visibles para ``user`` en las que el
    cliente participa con un papel vigente (lo mismo que lista
    ``GET /clients/{id}/applications``). Una subconsulta: sin consultas por fila."""
    participant_model = apps.get_model("applications", "ApplicationParticipant")
    participations = participant_model.objects.filter(client=OuterRef("pk"), is_active=True)
    condition = application_scope_condition(user, get_scope(user), prefix="application__")
    if condition is not None:
        participations = participations.filter(condition)
    count = (
        participations.order_by()
        .values("client")
        .annotate(total=Count("application", distinct=True))
        .values("total")
    )
    return clients.annotate(
        applications_count=Coalesce(Subquery(count, output_field=IntegerField()), 0)
    )


def _assigned_participations(user: User) -> QuerySet[Any]:
    """Participaciones del cliente en solicitudes asignadas al asesor.

    Incluye a los participantes retirados, para que el asesor pueda volver a agregarlos
    y consultar su historia. El broker no gana visibilidad por participación: nunca ve
    los participantes en detalle.

    `crm` no importa `applications` (la dependencia va en sentido contrario), por eso el
    modelo se resuelve por nombre.
    """
    participant_model = apps.get_model("applications", "ApplicationParticipant")
    return participant_model.objects.filter(
        client=OuterRef("pk"), application__assigned_advisor=user
    )


# --------------------------------------------------------------------------------------
# Clientes
# --------------------------------------------------------------------------------------


def _duplicate_client_error(user: User, document_type: CatalogItem, number: str) -> Exception:
    """Error de duplicado. Solo revela el cliente existente si el usuario puede verlo."""
    existing = clients_visible_to(user).filter(
        document_type_item=document_type, document_number=number
    )
    details: list[dict[str, Any]] = []
    existing_id = existing.values_list("pk", flat=True).first()
    if existing_id:
        details.append(
            {
                "field": "document_number",
                "code": "EXISTING_CLIENT",
                "message": "Usa el cliente existente.",
                "resource_id": str(existing_id),
            }
        )
    return DuplicateClientDocument(details=details)


def create_client(actor: User, data: dict[str, Any]) -> Client:
    try:
        with transaction.atomic():
            return Client.objects.create(created_by=actor, **data)
    except IntegrityError as exc:
        raise _duplicate_client_error(
            actor, data["document_type_item"], data["document_number"]
        ) from exc


def update_client(actor: User, client: Client, changes: dict[str, Any]) -> Client:
    if not changes:
        return client
    for field, value in changes.items():
        setattr(client, field, value)
    try:
        with transaction.atomic():
            client.save(update_fields=[*changes, "updated_at"])
    except IntegrityError as exc:
        raise _duplicate_client_error(
            actor, client.document_type_item, client.document_number
        ) from exc
    return client


# --------------------------------------------------------------------------------------
# Direcciones
# --------------------------------------------------------------------------------------


def _make_primary(address: ClientAddress) -> None:
    ClientAddress.objects.filter(client_id=address.client_id, is_primary=True).exclude(
        pk=address.pk
    ).update(is_primary=False)


def add_address(client: Client, data: dict[str, Any]) -> ClientAddress:
    """Agrega una dirección. La primera dirección del cliente queda como principal."""
    with transaction.atomic():
        is_first = not client.addresses.exists()
        is_primary = bool(data.pop("is_primary", False)) or is_first
        if is_primary:
            client.addresses.filter(is_primary=True).update(is_primary=False)
        return ClientAddress.objects.create(client=client, is_primary=is_primary, **data)


def update_address(address: ClientAddress, changes: dict[str, Any]) -> ClientAddress:
    if not changes:
        return address
    with transaction.atomic():
        if changes.get("is_primary"):
            _make_primary(address)
        for field, value in changes.items():
            setattr(address, field, value)
        address.save(update_fields=[*changes, "updated_at"])
    return address


def delete_address(address: ClientAddress) -> None:
    address.delete()


# --------------------------------------------------------------------------------------
# Oportunidades
# --------------------------------------------------------------------------------------


def resolve_visible_client(user: User, client_id: uuid.UUID) -> Client:
    client = clients_visible_to(user).filter(pk=client_id).first()
    if client is None:
        raise ValidationError({"client_id": ["El cliente no existe."]})
    return client


def resolve_project_for_opportunity(user: User, project_id: uuid.UUID | None) -> Project | None:
    """El proyecto debe ser visible para el usuario y estar ACTIVE."""
    if project_id is None:
        return None
    project = projects_visible_to(user).filter(pk=project_id).first()
    if project is None:
        raise ValidationError({"project_id": ["El proyecto no existe."]})
    ensure_project_accepts_opportunities(project)
    return project


def _ensure_no_open_duplicate(
    client: Client, project: Project | None, *, exclude_id: uuid.UUID | None = None
) -> None:
    duplicates = Opportunity.objects.filter(
        client=client, project=project, status__in=OPEN_OPPORTUNITY_STATUSES
    )
    if exclude_id is not None:
        duplicates = duplicates.exclude(pk=exclude_id)
    if duplicates.exists():
        raise DuplicateOpportunity()


# Motivo del registro en `opportunity_assignments` cuando el asesor crea la oportunidad.
SELF_ASSIGNMENT_REASON = "Asignación automática: la creó el asesor."


def create_opportunity(
    actor: User,
    *,
    client: Client,
    project: Project | None,
    origin_item: CatalogItem,
    notes: str = "",
) -> Opportunity:
    """Crea una oportunidad. Quien la crea queda como originador.

    Si el actor tiene rol `ADVISOR`, en la misma transacción queda asignada a él y pasa a
    `ASSIGNED` con la transición `NEW → ASSIGNED` (la misma de ``assign_advisor``), con su
    registro en `opportunity_assignments`. Si la crea un broker o el administrador, queda
    `NEW` y sin asesor. ``notes`` va a la actividad como la primera nota interna
    (``opportunity_created``).
    """
    self_assign = RoleCode.ADVISOR in get_access_profile(actor).roles
    transition: WorkflowTransition | None = None
    with transaction.atomic():
        # Bloquea al cliente para que dos peticiones simultáneas no creen duplicados.
        Client.objects.select_for_update().filter(pk=client.pk).first()
        _ensure_no_open_duplicate(client, project)
        if self_assign:
            transition = resolve_transition(
                actor,
                flow_type=FlowType.OPPORTUNITY,
                from_status=OpportunityStatus.NEW,
                to_status=OpportunityStatus.ASSIGNED,
            )
        opportunity = Opportunity.objects.create(
            client=client,
            project=project,
            origin_item=origin_item,
            origin_user=actor,
            assigned_advisor=actor if transition is not None else None,
            status=OpportunityStatus.ASSIGNED if transition is not None else OpportunityStatus.NEW,
        )
        if transition is not None:
            OpportunityAssignment.objects.create(
                opportunity=opportunity,
                advisor=actor,
                assigned_by=actor,
                reason=SELF_ASSIGNMENT_REASON,
            )

    opportunity_created.send(sender=Opportunity, opportunity=opportunity, actor=actor, notes=notes)
    if transition is not None:
        opportunity_assigned.send(
            sender=Opportunity,
            opportunity=opportunity,
            previous_advisor_id=None,
            advisor_id=actor.pk,
            actor=actor,
            reason=SELF_ASSIGNMENT_REASON,
        )
        opportunity_status_changed.send(
            sender=Opportunity,
            opportunity=opportunity,
            from_status=OpportunityStatus.NEW,
            to_status=OpportunityStatus.ASSIGNED,
            transition_code=transition.code,
            actor=actor,
            comment=SELF_ASSIGNMENT_REASON,
        )
    return opportunity


def update_opportunity(opportunity: Opportunity, changes: dict[str, Any]) -> Opportunity:
    if not opportunity.is_open:
        raise OpportunityNotEditable()
    if not changes:
        return opportunity
    with transaction.atomic():
        if "project" in changes:
            Client.objects.select_for_update().filter(pk=opportunity.client_id).first()
            _ensure_no_open_duplicate(
                opportunity.client, changes["project"], exclude_id=opportunity.pk
            )
        for field, value in changes.items():
            setattr(opportunity, field, value)
        opportunity.save(update_fields=[*changes, "updated_at"])
    return opportunity


def ensure_advisor(user: User) -> None:
    """El responsable de una oportunidad o solicitud es un usuario activo con rol ADVISOR."""
    roles = set(get_access_profile(user).roles)
    if not user.can_authenticate or RoleCode.ADVISOR not in roles:
        raise AdvisorNotEligible()


def assign_advisor(
    actor: User, opportunity: Opportunity, *, advisor: User, reason: str = ""
) -> Opportunity:
    """Asigna o reasigna el asesor responsable y conserva el historial.

    Si la oportunidad estaba en `NEW`, pasa a `ASSIGNED` con la transición `ASSIGN`.
    """
    ensure_advisor(advisor)
    with transaction.atomic():
        locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
        if not locked.is_open:
            raise OpportunityNotEditable()
        previous_advisor_id = locked.assigned_advisor_id
        if previous_advisor_id == advisor.pk:
            return locked

        transition = None
        if locked.status == OpportunityStatus.NEW:
            transition = resolve_transition(
                actor,
                flow_type=FlowType.OPPORTUNITY,
                from_status=OpportunityStatus.NEW,
                to_status=OpportunityStatus.ASSIGNED,
            )

        now = timezone.now()
        OpportunityAssignment.objects.filter(opportunity=locked, ended_at__isnull=True).update(
            ended_at=now
        )
        OpportunityAssignment.objects.create(
            opportunity=locked, advisor=advisor, assigned_by=actor, reason=reason
        )
        locked.assigned_advisor = advisor
        update_fields = ["assigned_advisor", "updated_at"]
        if transition is not None:
            locked.status = OpportunityStatus.ASSIGNED
            update_fields.append("status")
        locked.save(update_fields=update_fields)

    opportunity_assigned.send(
        sender=Opportunity,
        opportunity=locked,
        previous_advisor_id=previous_advisor_id,
        advisor_id=advisor.pk,
        actor=actor,
        reason=reason,
    )
    if transition is not None:
        opportunity_status_changed.send(
            sender=Opportunity,
            opportunity=locked,
            from_status=OpportunityStatus.NEW,
            to_status=OpportunityStatus.ASSIGNED,
            transition_code=transition.code,
            actor=actor,
            comment=reason,
        )
    return locked


def transition_opportunity(
    actor: User,
    opportunity: Opportunity,
    *,
    to_status: str,
    lost_reason: CatalogItem | None = None,
    comment: str = "",
) -> Opportunity:
    """Cambia el estado según las transiciones configuradas del flujo OPPORTUNITY."""
    if to_status == OpportunityStatus.ASSIGNED:
        raise ValidationError(
            {"target_status": ["Para asignar usa POST /opportunities/{id}/assignments."]}
        )
    if to_status == OpportunityStatus.CONVERTED:
        # Las transiciones `CONVERT_*` las ejecuta `applications` al crear la solicitud.
        raise ValidationError(
            {"target_status": ["La oportunidad se convierte al crear su solicitud."]}
        )
    if to_status == OpportunityStatus.LOST and lost_reason is None:
        raise ValidationError({"reason_code": ["El motivo es obligatorio para LOST."]})
    if to_status != OpportunityStatus.LOST and lost_reason is not None:
        raise ValidationError({"reason_code": ["El motivo solo aplica al estado LOST."]})

    with transaction.atomic():
        locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
        from_status = locked.status
        transition = resolve_transition(
            actor, flow_type=FlowType.OPPORTUNITY, from_status=from_status, to_status=to_status
        )
        locked.status = to_status
        locked.lost_reason_item = lost_reason
        locked.save(update_fields=["status", "lost_reason_item", "updated_at"])

    logger.info(
        "Oportunidad %s: %s → %s (%s) por %s",
        locked.pk,
        from_status,
        to_status,
        transition.code,
        actor.pk,
    )
    opportunity_status_changed.send(
        sender=Opportunity,
        opportunity=locked,
        from_status=from_status,
        to_status=to_status,
        transition_code=transition.code,
        actor=actor,
        comment=comment,
    )
    return locked


def convert_opportunity(actor: User, opportunity: Opportunity) -> Opportunity:
    """Pasa la oportunidad a `CONVERTED` con una transición `CONVERT_*`.

    La llama el módulo applications al crear la solicitud, dentro de su transacción y
    con la fila de la oportunidad ya bloqueada (``select_for_update``). Desde un estado
    sin transición de conversión (por ejemplo `NEW`) responde
    `409 INVALID_STATE_TRANSITION`. El evento sale solo si la transacción se confirma.
    """
    from_status = opportunity.status
    transition = resolve_transition(
        actor,
        flow_type=FlowType.OPPORTUNITY,
        from_status=from_status,
        to_status=OpportunityStatus.CONVERTED,
    )
    opportunity.status = OpportunityStatus.CONVERTED
    opportunity.converted_at = timezone.now()
    opportunity.save(update_fields=["status", "converted_at", "updated_at"])

    def _notify() -> None:
        opportunity_status_changed.send(
            sender=Opportunity,
            opportunity=opportunity,
            from_status=from_status,
            to_status=OpportunityStatus.CONVERTED,
            transition_code=transition.code,
            actor=actor,
            comment="",
        )

    transaction.on_commit(_notify)
    return opportunity


def available_actions(user: User, opportunity: Opportunity) -> list[WorkflowTransition]:
    """Transiciones que ``user`` puede ejecutar desde el estado actual (rol y permiso).

    Salen primero las principales, luego las secundarias y al final las destructivas
    (``apps.crm.actions``).
    """
    return sort_by_kind(
        available_transitions(user, flow_type=FlowType.OPPORTUNITY, from_status=opportunity.status)
    )
