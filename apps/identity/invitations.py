"""Invitaciones internas (sección 10.2 de la API).

Una invitación permite que un asesor, broker, administrador o miembro de una
constructora cree su propia contraseña. Al aceptarla:

1. se crea el usuario, o se vincula uno existente que aún no tiene contraseña
   (por ejemplo, creado por un administrador);
2. se le asigna el rol de la invitación;
3. si es para una constructora, se crea su membresía.

Este módulo está separado de ``services.py`` porque depende de ``partners``, y
``partners`` depende de ``identity.services``.
"""

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.identity.emails import send_invitation_email
from apps.identity.exceptions import (
    InvitationAlreadyPending,
    InvitationInvalid,
    InvitationNotPending,
    UserAlreadyExists,
)
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
from apps.identity.services import validate_new_password
from apps.identity.tokens import generate_opaque_token, hash_token
from apps.partners.exceptions import PartnerNotActive, UserAlreadyInPartner
from apps.partners.models import Partner
from apps.partners.services import add_member, get_active_membership


def invitations_queryset() -> QuerySet[InternalInvitation]:
    return InternalInvitation.objects.select_related("role", "partner", "invited_by")


def _ensure_email_can_be_invited(email: str, partner: Partner | None) -> None:
    user = User.objects.filter(email=email).first()
    if user is not None:
        # Solo se vincula una cuenta que nunca tuvo contraseña. Una invitación no
        # debe servir para tomar el control de una cuenta existente.
        if user.deleted_at is not None or user.has_usable_password():
            raise UserAlreadyExists()
        # Un usuario creado con `/users` ya puede ser miembro de esta misma constructora.
        membership = get_active_membership(user) if partner is not None else None
        if partner is not None and membership is not None and membership.partner_id != partner.pk:
            raise UserAlreadyInPartner()

    pending = InternalInvitation.objects.filter(
        invitation_status_filter(InvitationStatus.PENDING), email=email
    )
    if pending.exists():
        raise InvitationAlreadyPending()


def _validate_role_and_partner(role: Role, partner: Partner | None) -> None:
    if not role.is_active:
        raise ValidationError({"role": ["El rol no está activo."]})
    if role.code == RoleCode.CONSTRUCTION_PARTNER and partner is None:
        raise ValidationError(
            {"partner_id": ["Una invitación de constructora requiere la constructora."]}
        )
    if role.code != RoleCode.CONSTRUCTION_PARTNER and partner is not None:
        raise ValidationError(
            {"partner_id": ["Solo las invitaciones de constructora llevan constructora."]}
        )
    if partner is not None and not partner.is_active:
        raise PartnerNotActive()


def create_invitation(
    *, email: str, role: Role, partner: Partner | None, invited_by: User
) -> InternalInvitation:
    """Crea la invitación y envía el correo cuando se confirma la transacción."""
    email = UserManager.normalize_email(email)
    _validate_role_and_partner(role, partner)
    _ensure_email_can_be_invited(email, partner)

    raw_token = generate_opaque_token()
    with transaction.atomic():
        invitation = InternalInvitation.objects.create(
            email=email,
            token_hash=hash_token(raw_token),
            role=role,
            partner=partner,
            invited_by=invited_by,
            expires_at=timezone.now() + settings.AUTH_INVITATION_LIFETIME,
        )
        transaction.on_commit(
            lambda: send_invitation_email(invitation=invitation, raw_token=raw_token)
        )
    return invitation


def resend_invitation(invitation: InternalInvitation, *, actor: User) -> InternalInvitation:
    """Revoca el token anterior y envía una invitación nueva con los mismos datos.

    Sirve para invitaciones pendientes o vencidas. Vuelve a validar todo: si la
    constructora se desactivó o el correo ya tiene cuenta, el reenvío falla.
    """
    if invitation.status not in (InvitationStatus.PENDING, InvitationStatus.EXPIRED):
        raise InvitationNotPending()
    with transaction.atomic():
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
        return create_invitation(
            email=invitation.email,
            role=invitation.role,
            partner=invitation.partner,
            invited_by=actor,
        )


def revoke_invitation(invitation: InternalInvitation) -> InternalInvitation:
    """Revoca una invitación no aceptada. Es idempotente."""
    status = invitation.status
    if status == InvitationStatus.ACCEPTED:
        raise InvitationNotPending()
    if status != InvitationStatus.REVOKED:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
    return invitation


def accept_invitation(
    *,
    token: str,
    password: str,
    password_confirmation: str,
    first_name: str = "",
    last_name: str = "",
) -> User:
    """Consume el token, define la contraseña y deja al usuario listo para iniciar sesión."""
    if password != password_confirmation:
        raise ValidationError({"password_confirmation": ["Las contraseñas no coinciden."]})

    with transaction.atomic():
        invitation = (
            # `of=self`: PostgreSQL no permite FOR UPDATE sobre el LEFT JOIN opcional
            # de la constructora; basta con bloquear la invitación.
            InternalInvitation.objects.select_for_update(of=("self",))
            .select_related("role", "partner")
            .filter(token_hash=hash_token(token))
            .first()
        )
        if (
            invitation is None
            or invitation.status != InvitationStatus.PENDING
            or not invitation.role.is_active
        ):
            raise InvitationInvalid()
        if invitation.partner is not None and not invitation.partner.is_active:
            raise PartnerNotActive()

        user = User.objects.select_for_update().filter(email=invitation.email).first()
        if user is not None:
            if user.deleted_at is not None or user.has_usable_password():
                raise UserAlreadyExists()
            user.first_name = first_name or user.first_name
            user.last_name = last_name or user.last_name
        else:
            missing = {
                field: ["Este campo es requerido."]
                for field, value in (("first_name", first_name), ("last_name", last_name))
                if not value
            }
            if missing:
                raise ValidationError(missing)
            user = User(email=invitation.email, first_name=first_name, last_name=last_name)

        validate_new_password(password, user, "password")
        user.set_password(password)
        user.is_active = True
        user.save()

        UserRole.objects.get_or_create(
            user=user, role=invitation.role, defaults={"assigned_by": invitation.invited_by}
        )
        if invitation.partner is not None:
            membership = get_active_membership(user)
            if membership is None:
                add_member(invitation.partner, user=user, job_title="", started_at=None)
            elif membership.partner_id != invitation.partner_id:
                raise UserAlreadyInPartner()

        invitation.consumed_at = timezone.now()
        invitation.save(update_fields=["consumed_at", "updated_at"])
    return user
