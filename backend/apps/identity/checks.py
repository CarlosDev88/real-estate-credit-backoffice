"""Comprobaciones de arranque de las claves (SEC-03 de la auditoría de seguridad).

Sin ``DEBUG`` son errores: no corren ``runserver``, ``migrate`` ni ningún comando que haga
las comprobaciones, y la imagen ``production`` corre ``manage.py check`` antes de gunicorn
(que por sí solo no las hace). Con ``DEBUG`` (solo local) son avisos, para no bloquear a
quien todavía no regeneró su ``.env``.

Las claves se generan con ``python -c "import secrets; print(secrets.token_urlsafe(48))"``.
"""

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

# RFC 7518 §3.2: la clave de HS256 tiene al menos 256 bits.
JWT_KEY_MIN_BYTES = 32
# La misma regla de Django para `SECRET_KEY` (`security.W009`).
SECRET_KEY_MIN_LENGTH = 50
SECRET_KEY_MIN_UNIQUE_CHARACTERS = 5
SECRET_KEY_INSECURE_PREFIX = "django-insecure-"

GENERATE_HINT = 'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))"'


def _message(check_id: str, text: str) -> CheckMessage:
    level = Warning if settings.DEBUG else Error
    prefix = "W" if settings.DEBUG else "E"
    return level(text, hint=GENERATE_HINT, id=f"identity.{prefix}{check_id}")


def weak_secret_key(secret_key: str) -> bool:
    return (
        len(secret_key) < SECRET_KEY_MIN_LENGTH
        or len(set(secret_key)) < SECRET_KEY_MIN_UNIQUE_CHARACTERS
        or secret_key.startswith(SECRET_KEY_INSECURE_PREFIX)
    )


@register("security")
def check_signing_keys(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    messages: list[CheckMessage] = []
    jwt_key = str(settings.AUTH_JWT_SIGNING_KEY)
    if len(jwt_key.encode("utf-8")) < JWT_KEY_MIN_BYTES:
        messages.append(
            _message(
                "001",
                f"AUTH_JWT_SIGNING_KEY tiene menos de {JWT_KEY_MIN_BYTES} bytes "
                "(HS256 pide al menos 256 bits, RFC 7518 §3.2).",
            )
        )
    if weak_secret_key(str(settings.SECRET_KEY)):
        messages.append(
            _message(
                "002",
                f"DJANGO_SECRET_KEY es débil: necesita al menos {SECRET_KEY_MIN_LENGTH} "
                f"caracteres, {SECRET_KEY_MIN_UNIQUE_CHARACTERS} distintos y no empezar por "
                f'"{SECRET_KEY_INSECURE_PREFIX}".',
            )
        )
    return messages
