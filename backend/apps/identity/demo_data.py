"""Usuario inactivo e invitaciones de demo (``seed_demo_data``, TAREA-brechas-3-demo).

- ``inactivo@demo.local``: asesor desactivado por el administrador (no puede entrar).
- Invitaciones internas en sus cuatro estados: pendiente, aceptada (crea su usuario con la
  contraseña de demo), vencida y revocada.

Pasa por los servicios. Lo único que se escribe por fuera: el ``token_hash`` de la
invitación que se acepta (para conocer el token, que solo viaja por correo) y el
``expires_at`` de la vencida (no hay forma de "esperar" a que venza). Cada parte es
idempotente por su correo.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from apps.identity.invitations import accept_invitation, create_invitation, revoke_invitation
from apps.identity.models import InternalInvitation, Role, RoleCode, User
from apps.identity.tokens import hash_token
from apps.identity.users import create_user, set_user_active

DEMO_PASSWORD = "DemoUmbral2026!"
INACTIVE_EMAIL = "inactivo@demo.local"
# (correo, estado final)
INVITATIONS: tuple[tuple[str, str], ...] = (
    ("nueva.asesora@demo.local", "PENDING"),
    ("asesora.invitada@demo.local", "ACCEPTED"),
    ("invitacion.vencida@demo.local", "EXPIRED"),
    ("invitacion.revocada@demo.local", "REVOKED"),
)
# Token de la invitación que la demo acepta. Solo para correr en local.
ACCEPT_TOKEN = "demo-invitacion-aceptada-2026"


@dataclass
class IdentityResult:
    created: int = 0
    users: list[User] = field(default_factory=list)


def ensure_inactive_user(admin: User) -> tuple[User, bool]:
    existing = User.objects.filter(email=INACTIVE_EMAIL).first()
    if existing is not None:
        return existing, False
    user, _ = create_user(
        actor=admin,
        email=INACTIVE_EMAIL,
        first_name="Ricardo",
        last_name="Gil",
        phone="+573005550104",
        roles=[Role.objects.get(code=RoleCode.ADVISOR)],
        partner=None,
        send_invitation=False,
    )
    user.set_password(DEMO_PASSWORD)
    user.save(update_fields=["password", "updated_at"])
    set_user_active(user, active=False, actor=admin, reason="Ya no trabaja con nosotros.")
    return user, True


def _invite(admin: User, email: str, status: str) -> None:
    invitation = create_invitation(
        email=email, role=Role.objects.get(code=RoleCode.ADVISOR), partner=None, invited_by=admin
    )
    if status == "ACCEPTED":
        InternalInvitation.objects.filter(pk=invitation.pk).update(
            token_hash=hash_token(ACCEPT_TOKEN)
        )
        accept_invitation(
            token=ACCEPT_TOKEN,
            password=DEMO_PASSWORD,
            password_confirmation=DEMO_PASSWORD,
            first_name="Marcela",
            last_name="Ruiz",
        )
    elif status == "EXPIRED":
        # Se envió hace nueve días y venció hace dos (``expires_at > created_at``).
        now = timezone.now()
        InternalInvitation.objects.filter(pk=invitation.pk).update(
            created_at=now - timedelta(days=9),
            updated_at=now - timedelta(days=9),
            expires_at=now - timedelta(days=2),
        )
    elif status == "REVOKED":
        revoke_invitation(invitation)


def seed_invitations(admin: User) -> int:
    """Crea las invitaciones que falten (por correo). Devuelve cuántas creó."""
    created = 0
    for email, status in INVITATIONS:
        if InternalInvitation.objects.filter(email=email).exists():
            continue
        _invite(admin, email, status)
        created += 1
    return created
