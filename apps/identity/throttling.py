"""Límites de consumo de autenticación (sección 26 de la especificación).

Usan la caché ``default``, que en Docker es Redis, para que el límite se comparta
entre procesos y no viva en la memoria de cada uno.
"""

import hashlib
from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from apps.identity.models import UserManager

_PERIODS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class AuthRateThrottle(SimpleRateThrottle):
    """Throttle con tasas como ``"5/15m"`` y clave por IP más correo normalizado."""

    scope: str

    def get_rate(self) -> str:
        return str(settings.AUTH_RATE_LIMITS[self.scope])

    def parse_rate(self, rate: str | None) -> tuple[int, int]:
        assert rate is not None
        num, period = rate.split("/")
        multiplier = int(period[:-1] or 1)
        return int(num), multiplier * _PERIODS[period[-1]]

    def _hashed(self, value: str) -> str:
        # La clave de caché no guarda el correo en claro.
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _email_from_body(self, request: Request) -> str:
        data: Any = request.data
        email = data.get("email") if hasattr(data, "get") else None
        return UserManager.normalize_email(email if isinstance(email, str) else "")

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        ident = f"{self.get_ident(request)}|{self._email_from_body(request)}"
        return self.cache_format % {"scope": self.scope, "ident": self._hashed(ident)}


class LoginRateThrottle(AuthRateThrottle):
    scope = "login"


class PasswordResetRequestRateThrottle(AuthRateThrottle):
    scope = "password_reset_request"


class PasswordResetConfirmRateThrottle(AuthRateThrottle):
    scope = "password_reset_confirm"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self._hashed(self.get_ident(request)),
        }


class ChangePasswordRateThrottle(AuthRateThrottle):
    """Limita los intentos de adivinar la contraseña actual con una sesión robada."""

    scope = "change_password"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        user_id = getattr(request.user, "pk", None)
        if user_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(user_id)}


class InvitationAcceptRateThrottle(PasswordResetConfirmRateThrottle):
    """Limita por IP los intentos de adivinar tokens de invitación."""

    scope = "invitation_accept"
