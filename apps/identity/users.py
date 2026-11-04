"""Administración de usuarios internos y roles (sección 10.1 de la API).

Reglas:

- el correo normalizado es único;
- el comprador no se crea aquí: no es un usuario interno;
- un usuario de constructora (`CONSTRUCTION_PARTNER`) requiere membresía en una
  constructora, y ese rol no se combina con otros;
- desactivar revoca las sesiones y las invitaciones pendientes del usuario;
- un administrador no puede desactivarse ni quitarse el rol `ADMIN` a sí mismo.

Está separado de ``services.py`` porque depende de ``partners``.
"""

import logging
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, QuerySet
from django.dispatch import Signal
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.identity.exceptions import CannotModifyOwnAccount, EmailAlreadyRegistered
from apps.identity.invitations import create_invitation
from apps.identity.models import (
    InternalInvitation,
    InvitationStatus,
    Role,
    RoleCode,
    User,
    UserManager,
    UserRole,
    invitation_status_filter,
)
from apps.identity.services import revoke_user_sessions
from apps.partners.models import Partner, PartnerMembership, PartnerStatus
from apps.partners.services import add_member, end_membership, get_active_membership

logger = logging.getLogger(__name__)

# Argumentos: ``user``, ``from_status``, ``to_status``, ``actor`` y ``reason``.
user_status_changed = Signal()


def users_queryset() -> QuerySet[User]:
    return User.objects.filter(deleted_at__isnull=True).prefetch_related(
        Prefetch(
            "user_role_assignments",
            queryset=UserRole.objects.select_related("role").order_by("created_at"),
        ),
        Prefetch(
            "partner_memberships",
            queryset=PartnerMembership.objects.filter(
                status=PartnerStatus.ACTIVE, ended_at__isnull=True
            ).select_related("partner"),
            to_attr="active_memberships",
        ),
    )


def active_partner(user: User) -> Partner | None:
    """Constructora actual (usa el prefetch de ``users_queryset``)."""
    memberships = getattr(user, "active_memberships", None)
    if memberships is None:
        membership = get_active_membership(user)
        return membership.partner if membership else None
    return memberships[0].partner if memberships else None


def role_codes(user: User) -> list[str]:
    """Roles del usuario en orden de asignación (usa el prefetch de ``users_queryset``)."""
    return [assignment.role.code for assignment in user.user_role_assignments.all()]


def _validate_roles(roles: list[Role], partner: Partner | None, *, field: str) -> None:
    codes = {role.code for role in roles}
    inactive = sorted(role.code for role in roles if not role.is_active)
    if inactive:
        raise ValidationError({field: [f"Roles inactivos: {', '.join(inactive)}."]})
    if RoleCode.CONSTRUCTION_PARTNER in codes and len(codes) > 1:
        raise ValidationError(
            {field: ["El rol CONSTRUCTION_PARTNER no se combina con otros roles."]}
        )
    if RoleCode.CONSTRUCTION_PARTNER not in codes and partner is not None:
        raise ValidationError(
            {"partner_id": ["Solo un usuario de constructora lleva constructora."]}
        )


def _set_roles(user: User, roles: list[Role], *, actor: User) -> None:
    UserRole.objects.filter(user=user).exclude(role__in=roles).delete()
    existing = set(UserRole.objects.filter(user=user).values_list("role_id", flat=True))
    UserRole.objects.bulk_create(
        [
            UserRole(user=user, role=role, assigned_by=actor)
            for role in roles
            if role.pk not in existing
        ]
    )


def create_user(
    *,
    actor: User,
    email: str,
    first_name: str,
    last_name: str,
    phone: str,
    roles: list[Role],
    partner: Partner | None,
    send_invitation: bool,
) -> tuple[User, InternalInvitation | None]:
    """Crea un usuario sin contraseña (estado `PENDING`) y, si se pide, lo invita.

    El usuario define su contraseña al aceptar la invitación. Si no se envía ahora,
    se puede invitar después con `POST /invitations`.
    """
    _validate_roles(roles, partner, field="role_codes")
    is_partner_user = any(role.code == RoleCode.CONSTRUCTION_PARTNER for role in roles)
    if is_partner_user and partner is None:
        raise ValidationError(
            {"partner_id": ["Un usuario de constructora requiere la constructora."]}
        )

    email = UserManager.normalize_email(email)
    with transaction.atomic():
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=None,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                )
        except IntegrityError as exc:
            raise EmailAlreadyRegistered() from exc

        _set_roles(user, roles, actor=actor)
        if partner is not None:
            add_member(partner, user=user, job_title="", started_at=None)

        invitation = None
        if send_invitation:
            invitation = create_invitation(
                email=email, role=roles[0], partner=partner, invited_by=actor
            )
    return user, invitation


def update_user(user: User, changes: dict[str, Any]) -> User:
    if changes:
        for field, value in changes.items():
            setattr(user, field, value)
        user.save(update_fields=[*changes, "updated_at"])
    return user


def replace_roles(user: User, roles: list[Role], *, actor: User, partner: Partner | None) -> User:
    """Reemplaza los roles del usuario y ajusta su membresía de constructora.

    - Si recibe `CONSTRUCTION_PARTNER` y el usuario no es miembro, `partner_id` es
      obligatorio y se crea la membresía.
    - Si pierde `CONSTRUCTION_PARTNER`, su membresía activa se finaliza.
    """
    _validate_roles(roles, partner, field="role_codes")
    codes = {role.code for role in roles}
    if user.pk == actor.pk and RoleCode.ADMIN not in codes and _has_role(user, RoleCode.ADMIN):
        raise CannotModifyOwnAccount()

    with transaction.atomic():
        membership = get_active_membership(user)
        if RoleCode.CONSTRUCTION_PARTNER in codes:
            if membership is None and partner is None:
                raise ValidationError(
                    {"partner_id": ["Un usuario de constructora requiere la constructora."]}
                )
            if (
                membership is not None
                and partner is not None
                and membership.partner_id != partner.pk
            ):
                raise ValidationError(
                    {"partner_id": ["El usuario ya es miembro de otra constructora."]}
                )
            _set_roles(user, roles, actor=actor)
            if membership is None:
                assert partner is not None
                add_member(partner, user=user, job_title="", started_at=None)
        else:
            _set_roles(user, roles, actor=actor)
            if membership is not None:
                end_membership(membership)
    return user


def _has_role(user: User, code: str) -> bool:
    return UserRole.objects.filter(user=user, role__code=code).exists()


def set_user_active(user: User, *, active: bool, actor: User, reason: str = "") -> User:
    """Activa o desactiva el usuario. Desactivar corta su acceso de inmediato."""
    if not active and user.pk == actor.pk:
        raise CannotModifyOwnAccount()
    previous = user.status
    if user.is_active == active:
        return user

    with transaction.atomic():
        user.is_active = active
        user.save(update_fields=["is_active", "updated_at"])
        if not active:
            revoke_user_sessions(user)
            InternalInvitation.objects.filter(
                invitation_status_filter(InvitationStatus.PENDING), email=user.email
            ).update(revoked_at=timezone.now())

    logger.info(
        "Usuario %s: %s → %s por %s. Motivo: %s",
        user.pk,
        previous,
        user.status,
        actor.pk,
        reason or "-",
    )
    user_status_changed.send(
        sender=User,
        user=user,
        from_status=previous,
        to_status=user.status,
        actor=actor,
        reason=reason,
    )
    return user
