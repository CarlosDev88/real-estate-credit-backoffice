"""Casos de uso del módulo partners: constructoras, membresías y proyectos.

Alcance por rol (secciones 3 y 8.6 de los requerimientos, 11 y 12 de la API):

- ``ADMIN`` y ``ADVISOR`` ven todas las constructoras y todos los proyectos.
- ``CONSTRUCTION_PARTNER`` solo ve su constructora, su propia membresía y los
  proyectos de su constructora. El partner se deriva de su membresía activa: un
  ``partner_id`` enviado por el cliente nunca amplía su alcance.
- ``INDEPENDENT_BROKER`` solo ve proyectos ``ACTIVE``, para asociarlos a oportunidades.

Un recurso fuera del alcance responde 404, para no confirmar que existe.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalogs.models import WorkflowTransition
from apps.catalogs.services import available_transitions
from apps.catalogs.workflow import FlowType, ProjectStatus
from apps.identity.models import RoleCode, User
from apps.identity.services import get_access_profile
from apps.partners.exceptions import (
    DuplicateProjectName,
    DuplicateTaxId,
    InvalidStateTransition,
    MembershipEnded,
    OutOfScope,
    PartnerNotActive,
    ProjectNotActive,
    ProjectNotEditable,
    UserAlreadyInPartner,
    UserNotEligible,
)
from apps.partners.models import Partner, PartnerMembership, PartnerStatus, Project
from apps.partners.signals import partner_status_changed, project_status_changed

logger = logging.getLogger(__name__)

_GLOBAL_SCOPE_ROLES = {RoleCode.ADMIN, RoleCode.ADVISOR}


# --------------------------------------------------------------------------------------
# Alcance
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PartnerScope:
    sees_everything: bool
    is_partner_user: bool
    is_broker: bool
    membership: PartnerMembership | None

    @property
    def partner_id(self) -> uuid.UUID | None:
        return self.membership.partner_id if self.membership else None


def get_active_membership(user: User) -> PartnerMembership | None:
    return (
        PartnerMembership.objects.select_related("partner")
        .filter(user=user, status=PartnerStatus.ACTIVE, ended_at__isnull=True)
        .first()
    )


def get_scope(user: User) -> PartnerScope:
    roles = set(get_access_profile(user).roles)
    sees_everything = user.is_superuser or bool(roles & _GLOBAL_SCOPE_ROLES)
    is_partner_user = not sees_everything and RoleCode.CONSTRUCTION_PARTNER in roles
    return PartnerScope(
        sees_everything=sees_everything,
        is_partner_user=is_partner_user,
        is_broker=not sees_everything
        and not is_partner_user
        and RoleCode.INDEPENDENT_BROKER in roles,
        membership=get_active_membership(user) if is_partner_user else None,
    )


def partners_visible_to(user: User) -> QuerySet[Partner]:
    partners = Partner.objects.filter(deleted_at__isnull=True)
    scope = get_scope(user)
    if scope.sees_everything:
        return partners
    if scope.partner_id:
        return partners.filter(pk=scope.partner_id)
    return partners.none()


def memberships_visible_to(user: User) -> QuerySet[PartnerMembership]:
    memberships = PartnerMembership.objects.select_related("partner", "user")
    scope = get_scope(user)
    if scope.sees_everything:
        return memberships
    if scope.is_partner_user:
        return memberships.filter(user=user)
    return memberships.none()


def projects_visible_to(user: User) -> QuerySet[Project]:
    projects = Project.objects.filter(deleted_at__isnull=True).select_related(
        "partner", "city_item__parent_item", "created_by", "validated_by"
    )
    scope = get_scope(user)
    if scope.sees_everything:
        return projects
    if scope.partner_id:
        return projects.filter(partner_id=scope.partner_id)
    if scope.is_broker:
        return projects.filter(
            status=ProjectStatus.ACTIVE,
            partner__status=PartnerStatus.ACTIVE,
            partner__deleted_at__isnull=True,
        )
    return projects.none()


# --------------------------------------------------------------------------------------
# Constructoras
# --------------------------------------------------------------------------------------


def create_partner(data: dict[str, Any]) -> Partner:
    try:
        with transaction.atomic():
            return Partner.objects.create(**data)
    except IntegrityError as exc:
        raise DuplicateTaxId() from exc


def update_partner(partner: Partner, changes: dict[str, Any]) -> Partner:
    if changes:
        for field, value in changes.items():
            setattr(partner, field, value)
        partner.save(update_fields=[*changes, "updated_at"])
    return partner


def set_partner_status(partner: Partner, *, active: bool, actor: User, reason: str = "") -> Partner:
    target = PartnerStatus.ACTIVE if active else PartnerStatus.INACTIVE
    previous = partner.status
    if previous == target:
        return partner
    partner.status = target
    partner.save(update_fields=["status", "updated_at"])
    logger.info(
        "Constructora %s: %s → %s por %s. Motivo: %s",
        partner.pk,
        previous,
        target,
        actor.pk,
        reason or "-",
    )
    partner_status_changed.send(
        sender=Partner,
        partner=partner,
        from_status=previous,
        to_status=target,
        actor=actor,
        reason=reason,
    )
    return partner


def partner_metrics(partner: Partner) -> dict[str, Any]:
    by_status = {
        row["status"]: row["total"]
        for row in partner.projects.filter(deleted_at__isnull=True)
        .values("status")
        .annotate(total=Count("id"))
    }
    return {
        "projects_by_status": {status: by_status.get(status, 0) for status in ProjectStatus.values},
        "active_members": partner.memberships.filter(
            status=PartnerStatus.ACTIVE, ended_at__isnull=True
        ).count(),
    }


# --------------------------------------------------------------------------------------
# Membresías
# --------------------------------------------------------------------------------------


def add_member(
    partner: Partner, *, user: User, job_title: str, started_at: date | None
) -> PartnerMembership:
    if not partner.is_active:
        raise PartnerNotActive()
    roles = set(get_access_profile(user).roles)
    if not user.can_authenticate or RoleCode.CONSTRUCTION_PARTNER not in roles:
        raise UserNotEligible()
    if get_active_membership(user) is not None:
        raise UserAlreadyInPartner()
    try:
        with transaction.atomic():
            return PartnerMembership.objects.create(
                partner=partner,
                user=user,
                job_title=job_title,
                started_at=started_at or timezone.localdate(),
            )
    except IntegrityError as exc:
        raise UserAlreadyInPartner() from exc


def update_membership(membership: PartnerMembership, changes: dict[str, Any]) -> PartnerMembership:
    if membership.ended_at is not None:
        raise MembershipEnded()
    if not changes:
        return membership
    for field, value in changes.items():
        setattr(membership, field, value)
    try:
        with transaction.atomic():
            membership.save(update_fields=[*changes, "updated_at"])
    except IntegrityError as exc:
        raise UserAlreadyInPartner() from exc
    return membership


def end_membership(membership: PartnerMembership) -> PartnerMembership:
    """Finaliza la membresía sin borrarla. Es idempotente."""
    if membership.ended_at is not None:
        return membership
    membership.status = PartnerStatus.INACTIVE
    membership.ended_at = max(timezone.localdate(), membership.started_at)
    membership.save(update_fields=["status", "ended_at", "updated_at"])
    return membership


# --------------------------------------------------------------------------------------
# Proyectos
# --------------------------------------------------------------------------------------


def _save_project(project: Project, update_fields: list[str] | None = None) -> None:
    try:
        with transaction.atomic():
            project.save(update_fields=update_fields)
    except IntegrityError as exc:
        raise DuplicateProjectName() from exc


def create_project(user: User, data: dict[str, Any]) -> Project:
    """Crea un proyecto en `DRAFT`. Para una constructora, el partner sale de su membresía."""
    scope = get_scope(user)
    # Para la constructora se ignora: nunca se valida ni se usa un partner_id ajeno.
    requested_partner_id = data.pop("partner_id", None)

    if scope.sees_everything:
        if requested_partner_id is None:
            raise ValidationError({"partner_id": ["Este campo es requerido."]})
        partner = Partner.objects.filter(pk=requested_partner_id, deleted_at__isnull=True).first()
        if partner is None:
            raise ValidationError({"partner_id": ["La constructora no existe."]})
    elif scope.is_partner_user:
        if scope.membership is None:
            raise OutOfScope()
        partner = scope.membership.partner
    else:
        raise PermissionDenied()

    if not partner.is_active:
        raise PartnerNotActive()

    project = Project(partner=partner, created_by=user, status=ProjectStatus.DRAFT, **data)
    _save_project(project)
    return project


def update_project(user: User, project: Project, changes: dict[str, Any]) -> Project:
    """Edita los datos del proyecto.

    La constructora solo edita sus proyectos en `DRAFT` (RF-17). Asesor y
    administrador pueden corregir cualquier proyecto que no esté archivado.
    """
    if project.status == ProjectStatus.ARCHIVED:
        raise ProjectNotEditable("Un proyecto archivado no se puede editar.")

    scope = get_scope(user)
    if not scope.sees_everything:
        if project.status != ProjectStatus.DRAFT:
            raise ProjectNotEditable("La constructora solo puede editar proyectos en borrador.")
        if not project.partner.is_active:
            raise PartnerNotActive()

    if changes:
        for field, value in changes.items():
            setattr(project, field, value)
        _save_project(project, update_fields=[*changes, "updated_at"])
    return project


def _transitions_for(user: User, project: Project) -> QuerySet[WorkflowTransition]:
    return available_transitions(user, flow_type=FlowType.PROJECT, from_status=project.status)


def available_actions(user: User, project: Project) -> list[str]:
    """Códigos de las transiciones que ``user`` puede ejecutar ahora sobre el proyecto."""
    if not get_scope(user).sees_everything and not project.partner.is_active:
        return []
    return list(_transitions_for(user, project).values_list("code", flat=True))


def transition_project(
    user: User, project: Project, *, to_status: str, reason: str = ""
) -> Project:
    """Cambia el estado del proyecto según las transiciones configuradas.

    - Si no existe ninguna transición activa entre el estado actual y el destino:
      `409 INVALID_STATE_TRANSITION`.
    - Si existe, pero el usuario no tiene el rol o el permiso: `403`.
    """
    with transaction.atomic():
        locked = Project.objects.select_for_update().select_related("partner").get(pk=project.pk)
        from_status = locked.status

        transition = _transitions_for(user, locked).filter(to_status=to_status).first()
        if transition is None:
            configured = WorkflowTransition.objects.filter(
                flow_type=FlowType.PROJECT,
                from_status=from_status,
                to_status=to_status,
                is_active=True,
            ).exists()
            if configured:
                raise PermissionDenied()
            raise InvalidStateTransition(f"No se puede pasar de {from_status} a {to_status}.")

        if not get_scope(user).sees_everything and not locked.partner.is_active:
            raise PartnerNotActive()

        locked.status = to_status
        update_fields = ["status", "updated_at"]
        if to_status == ProjectStatus.ACTIVE:
            locked.validated_by = user
            locked.validated_at = timezone.now()
            update_fields += ["validated_by", "validated_at"]
        _save_project(locked, update_fields=update_fields)

    logger.info(
        "Proyecto %s: %s → %s (%s) por %s. Motivo: %s",
        locked.pk,
        from_status,
        to_status,
        transition.code,
        user.pk,
        reason or "-",
    )
    project_status_changed.send(
        sender=Project,
        project=locked,
        from_status=from_status,
        to_status=to_status,
        transition_code=transition.code,
        actor=user,
        reason=reason,
    )
    return locked


def ensure_project_accepts_opportunities(project: Project) -> None:
    """Regla para el módulo crm (paso 5): solo un proyecto activo recibe oportunidades."""
    if (
        project.status != ProjectStatus.ACTIVE
        or project.deleted_at is not None
        or not project.partner.is_active
    ):
        raise ProjectNotActive()
