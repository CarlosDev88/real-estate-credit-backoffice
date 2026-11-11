import math
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail

from apps.identity.models import BuyerAccessLink, InternalInvitation, User

if TYPE_CHECKING:
    from apps.crm.models import Client


def build_password_reset_url(raw_token: str) -> str:
    return f"{settings.PASSWORD_RESET_URL}?{urlencode({'token': raw_token})}"


def send_password_reset_email(*, user: User, raw_token: str) -> None:
    """Envía el enlace de recuperación.

    Por ahora el envío es síncrono, al confirmar la transacción. Cuando exista el
    worker de Celery y el outbox (módulo notifications), debe pasar a una tarea.
    """
    minutes = int(settings.AUTH_PASSWORD_RESET_TOKEN_LIFETIME.total_seconds() // 60)
    reset_url = build_password_reset_url(raw_token)
    send_mail(
        subject="Restablece tu contraseña",
        message=(
            f"Hola {user.first_name},\n\n"
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta.\n"
            f"Abre este enlace para definir una nueva (vence en {minutes} minutos):\n\n"
            f"{reset_url}\n\n"
            "Si no hiciste esta solicitud, ignora este correo; tu contraseña no cambiará.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def build_invitation_url(raw_token: str) -> str:
    return f"{settings.INVITATION_ACCEPT_URL}?{urlencode({'token': raw_token})}"


def send_invitation_email(*, invitation: InternalInvitation, raw_token: str) -> None:
    """Envía la invitación interna. Igual que la recuperación, por ahora es síncrono."""
    hours = int(settings.AUTH_INVITATION_LIFETIME.total_seconds() // 3600)
    partner_line = (
        f"Te unirás al equipo de {invitation.partner}.\n" if invitation.partner_id else ""
    )
    send_mail(
        subject="Invitación a la plataforma de crédito de vivienda",
        message=(
            "Hola,\n\n"
            f"Te invitaron a la plataforma con el rol {invitation.role.name}.\n"
            f"{partner_line}"
            f"Abre este enlace para crear tu contraseña (vence en {hours} horas):\n\n"
            f"{build_invitation_url(raw_token)}\n\n"
            "Si no esperabas esta invitación, ignora este correo.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )


def build_buyer_access_url(raw_token: str) -> str:
    return f"{settings.BUYER_ACCESS_URL}?{urlencode({'token': raw_token})}"


def send_buyer_access_email(*, client: "Client", link: BuyerAccessLink, raw_token: str) -> None:
    """Envía el enlace de acceso al titular. Por ahora es síncrono, como los demás.

    Siguiendo REQUERIMIENTOS §9.2, no incluye datos del expediente: solo el saludo, el
    enlace y su vencimiento.
    """
    hours = math.ceil((link.expires_at - link.created_at).total_seconds() / 3600)
    send_mail(
        subject="Tu acceso al portal de crédito de vivienda",
        message=(
            f"Hola {client.first_names},\n\n"
            "Te invitamos a continuar tu solicitud de crédito de vivienda en el portal.\n"
            "No necesitas crear una cuenta ni una contraseña: abre este enlace, que solo "
            f"se puede usar una vez y vence en {hours} horas:\n\n"
            f"{build_buyer_access_url(raw_token)}\n\n"
            "No compartas este enlace. Si no esperabas este correo, ignóralo.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
    )
