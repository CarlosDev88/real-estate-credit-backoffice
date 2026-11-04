"""Casos de uso de autenticación interna: login, refresh, logout y contraseñas.

Las vistas solo traducen HTTP; las reglas viven aquí para poder probarlas y
reutilizarlas (por ejemplo, desde tareas o comandos de administración).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.contrib.auth import user_logged_in, user_logged_out, user_login_failed
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.identity.emails import send_password_reset_email
from apps.identity.exceptions import (
    InvalidCredentials,
    InvalidCurrentPassword,
    PasswordResetTokenInvalid,
    RefreshSessionExpired,
    UserInactive,
)
from apps.identity.models import (
    AuthSession,
    PasswordResetToken,
    Permission,
    RoleCode,
    User,
    UserManager,
    UserRole,
)
from apps.identity.tokens import generate_opaque_token, hash_token, issue_access_token

logger = logging.getLogger(__name__)

USER_AGENT_MAX_LENGTH = 255

# Roles que solo ven los expedientes asignados u originados por ellos (sección 3).
_ASSIGNED_SCOPE_ROLES = {RoleCode.ADVISOR, RoleCode.INDEPENDENT_BROKER}


# --------------------------------------------------------------------------------------
# Resultados
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class IssuedSession:
    """Sesión recién creada o rotada, con los tokens en claro para las cookies."""

    session: AuthSession
    access_token: str
    access_expires_at: datetime
    refresh_token: str

    @property
    def refresh_expires_at(self) -> datetime:
        return self.session.expires_at


@dataclass(frozen=True)
class AccessProfile:
    """Rol, permisos y alcance que el frontend usa para mostrar u ocultar funciones."""

    role: str | None
    roles: list[str]
    permissions: list[str]
    assigned_applications_only: bool
    partner_id: uuid.UUID | None = None


# --------------------------------------------------------------------------------------
# Utilidades de petición
# --------------------------------------------------------------------------------------


def client_ip(request: HttpRequest) -> str | None:
    """IP del cliente sin confiar ciegamente en ``X-Forwarded-For`` (sección 9.5).

    Solo se lee ``X-Forwarded-For`` cuando hay proxies de confianza configurados en
    ``REST_FRAMEWORK["NUM_PROXIES"]``; se usa la misma regla que los throttles de DRF.
    """
    num_proxies = settings.REST_FRAMEWORK.get("NUM_PROXIES") or 0
    remote_addr = request.META.get("REMOTE_ADDR")
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if num_proxies and xff:
        addresses = [address.strip() for address in xff.split(",") if address.strip()]
        if addresses:
            return addresses[-min(num_proxies, len(addresses))]
    return remote_addr or None


def _user_agent_summary(request: HttpRequest) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX_LENGTH]


# --------------------------------------------------------------------------------------
# Roles y permisos
# --------------------------------------------------------------------------------------


def _active_partner_id(user: User) -> uuid.UUID | None:
    """Constructora de la membresía activa del usuario.

    `identity` no importa `partners` (la dependencia va en sentido contrario), por eso
    el modelo se resuelve por nombre.
    """
    if not apps.is_installed("apps.partners"):
        return None
    membership_model = apps.get_model("partners", "PartnerMembership")
    membership = (
        membership_model.objects.filter(user=user, status="ACTIVE", ended_at__isnull=True)
        .only("partner_id")
        .first()
    )
    return membership.partner_id if membership else None


def get_access_profile(user: User) -> AccessProfile:
    assignments = (
        UserRole.objects.filter(user=user, role__is_active=True)
        .select_related("role")
        .order_by("created_at")
    )
    roles = [assignment.role.code for assignment in assignments]

    if user.is_superuser:
        permission_qs = Permission.objects.all()
    else:
        permission_qs = Permission.objects.filter(
            role_assignments__role__user_assignments__user=user,
            role_assignments__role__is_active=True,
        )
    permissions = sorted(set(permission_qs.values_list("code", flat=True)))

    is_admin = user.is_superuser or RoleCode.ADMIN in roles
    assigned_only = not is_admin and any(role in _ASSIGNED_SCOPE_ROLES for role in roles)

    return AccessProfile(
        role=roles[0] if roles else None,
        roles=roles,
        permissions=permissions,
        assigned_applications_only=assigned_only,
        partner_id=_active_partner_id(user) if RoleCode.CONSTRUCTION_PARTNER in roles else None,
    )


# --------------------------------------------------------------------------------------
# Sesiones
# --------------------------------------------------------------------------------------


def _create_session(
    *,
    user: User,
    request: HttpRequest,
    expires_at: datetime,
    rotated_from: AuthSession | None = None,
) -> IssuedSession:
    refresh_token = generate_opaque_token()
    session = AuthSession.objects.create(
        user=user,
        refresh_token_hash=hash_token(refresh_token),
        expires_at=expires_at,
        rotated_from=rotated_from,
        ip_address=client_ip(request),
        user_agent_summary=_user_agent_summary(request),
    )
    access_token, access_expires_at = issue_access_token(user_id=user.pk, session_id=session.pk)
    # El access token nunca debe sobrevivir a su sesión.
    access_expires_at = min(access_expires_at, session.expires_at)
    return IssuedSession(
        session=session,
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
    )


def login(*, request: HttpRequest, email: str, password: str) -> tuple[User, IssuedSession]:
    """Valida credenciales internas y abre una sesión nueva.

    No revela si el correo existe: un correo desconocido y una contraseña incorrecta
    responden igual y tardan lo mismo (se calcula un hash aunque no haya usuario).
    """
    normalized_email = UserManager.normalize_email(email)
    user = User.objects.filter(email=normalized_email, deleted_at__isnull=True).first()

    if user is None:
        User().set_password(password)  # Iguala el tiempo de respuesta.
        user_login_failed.send(
            sender=User, credentials={"email": normalized_email}, request=request
        )
        raise InvalidCredentials()

    if not user.check_password(password):
        user_login_failed.send(
            sender=User, credentials={"email": normalized_email}, request=request
        )
        raise InvalidCredentials()

    if not user.is_active:
        raise UserInactive()

    with transaction.atomic():
        issued = _create_session(
            user=user,
            request=request,
            expires_at=timezone.now() + settings.AUTH_REFRESH_TOKEN_LIFETIME,
        )
    # Actualiza `last_login` y deja el punto de enganche para la auditoría.
    user_logged_in.send(sender=User, request=request, user=user)
    return user, issued


def _revoke_descendants(session: AuthSession, moment: datetime) -> None:
    """Revoca todas las sesiones que nacieron de ``session`` por rotación."""
    current = session
    while True:
        child = AuthSession.objects.select_for_update().filter(rotated_from=current).first()
        if child is None:
            return
        if child.revoked_at is None:
            child.revoked_at = moment
            child.save(update_fields=["revoked_at"])
        current = child


def refresh_session(*, request: HttpRequest, refresh_token: str | None) -> IssuedSession:
    """Rota el refresh token: revoca la sesión actual y emite una nueva.

    El refresh es de un solo uso. Si llega un token que ya fue rotado, se asume que
    fue robado y se revoca toda la cadena de sesiones derivada de él.

    La rotación conserva el vencimiento absoluto de la sesión original: refrescar no
    extiende la sesión más allá de ``AUTH_REFRESH_TOKEN_LIFETIME`` desde el login.
    """
    if not refresh_token:
        raise RefreshSessionExpired()

    now = timezone.now()
    reuse_detected = False

    with transaction.atomic():
        session = (
            AuthSession.objects.select_for_update()
            .select_related("user")
            .filter(refresh_token_hash=hash_token(refresh_token))
            .first()
        )
        if session is None:
            raise RefreshSessionExpired()

        if session.revoked_at is not None:
            if AuthSession.objects.filter(rotated_from=session).exists():
                _revoke_descendants(session, now)
                reuse_detected = True
        elif session.expires_at > now and session.user.can_authenticate:
            session.revoked_at = now
            session.save(update_fields=["revoked_at"])
            return _create_session(
                user=session.user,
                request=request,
                expires_at=session.expires_at,
                rotated_from=session,
            )

    if reuse_detected:
        logger.warning(
            "Reutilización de refresh token detectada; se revocó la cadena de la sesión %s",
            session.pk,
        )
    raise RefreshSessionExpired()


def logout(*, request: HttpRequest, refresh_token: str | None) -> None:
    """Revoca la sesión del refresh token, si sigue activa. Es idempotente."""
    if not refresh_token:
        return
    session = (
        AuthSession.objects.select_related("user")
        .filter(refresh_token_hash=hash_token(refresh_token), revoked_at__isnull=True)
        .first()
    )
    if session is None:
        return
    AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    user_logged_out.send(sender=User, request=request, user=session.user)


def revoke_user_sessions(user: User, *, except_session_id: uuid.UUID | None = None) -> int:
    sessions = AuthSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_session_id is not None:
        sessions = sessions.exclude(pk=except_session_id)
    return sessions.update(revoked_at=timezone.now())


# --------------------------------------------------------------------------------------
# Contraseñas
# --------------------------------------------------------------------------------------


def validate_new_password(password: str, user: User, field_name: str) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({field_name: list(exc.messages)}) from exc


def request_password_reset(*, request: HttpRequest, email: str) -> None:
    """Crea un token de recuperación y envía el correo, si el usuario existe.

    La respuesta HTTP es la misma exista o no el correo, para no revelar usuarios.
    """
    normalized_email = UserManager.normalize_email(email)
    user = User.objects.filter(
        email=normalized_email, is_active=True, deleted_at__isnull=True
    ).first()
    if user is None:
        return

    raw_token = generate_opaque_token()
    now = timezone.now()
    with transaction.atomic():
        # Solo el enlace más reciente queda vigente.
        PasswordResetToken.objects.filter(
            user=user, consumed_at__isnull=True, expires_at__gt=now
        ).update(consumed_at=now)
        PasswordResetToken.objects.create(
            user=user,
            token_hash=hash_token(raw_token),
            expires_at=now + settings.AUTH_PASSWORD_RESET_TOKEN_LIFETIME,
            requested_ip=client_ip(request),
        )
        transaction.on_commit(lambda: send_password_reset_email(user=user, raw_token=raw_token))


def confirm_password_reset(*, token: str, new_password: str) -> User:
    """Cambia la contraseña con un token de un solo uso y revoca todas las sesiones."""
    now = timezone.now()
    with transaction.atomic():
        reset_token = (
            PasswordResetToken.objects.select_for_update()
            .select_related("user")
            .filter(token_hash=hash_token(token))
            .first()
        )
        if (
            reset_token is None
            or not reset_token.is_usable_at(now)
            or not reset_token.user.can_authenticate
        ):
            raise PasswordResetTokenInvalid()

        user = reset_token.user
        validate_new_password(new_password, user, "new_password")

        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        PasswordResetToken.objects.filter(user=user, consumed_at__isnull=True).update(
            consumed_at=now
        )
        revoke_user_sessions(user)
    return user


def change_password(
    *, user: User, current_session: AuthSession, current_password: str, new_password: str
) -> None:
    """Cambia la contraseña del usuario autenticado y revoca sus otras sesiones."""
    if not user.check_password(current_password):
        raise InvalidCurrentPassword()
    if current_password == new_password:
        raise ValidationError(
            {"new_password": ["La nueva contraseña debe ser distinta de la actual."]}
        )
    validate_new_password(new_password, user, "new_password")

    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        revoke_user_sessions(user, except_session_id=current_session.pk)
