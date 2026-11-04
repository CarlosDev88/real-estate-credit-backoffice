from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail

from apps.identity.models import User


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
