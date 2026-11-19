"""Límites de consumo de la API (sección 26 de la especificación y REQUERIMIENTOS §9.3).

Usan la caché ``default``, que en Docker es Redis, para que el límite se comparta
entre procesos y no viva en la memoria de cada uno.

Hay dos familias:

- los **generales** (``GENERAL_THROTTLES``, también en ``DEFAULT_THROTTLE_CLASSES``):
  lecturas y escrituras por usuario interno, por sesión del comprador o, sin sesión, por
  IP, más el de cambios de estado y radicaciones de las vistas con ``throttle_scope``;
- los **propios** de cada flujo sensible (login, recuperación, enlaces, cargas,
  descargas, reportes). Una vista con límites propios los suma a los generales:
  ``throttle_classes = [*GENERAL_THROTTLES, LoginRateThrottle, ...]``.
"""

import hashlib
from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle

from apps.identity.models import BuyerSession, UserManager

_PERIODS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Lo que cuenta como lectura para los límites generales; el resto es escritura.
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def rate_multiplier() -> int:
    """Cuánto se agrandan los cupos: ``AUTH_RATE_LIMIT_MULTIPLIER`` solo con ``DEBUG``
    (los E2E locales hacen muchos logins). Con ``DEBUG=False`` siempre es 1."""
    if not settings.DEBUG:
        return 1
    return max(1, int(settings.AUTH_RATE_LIMIT_MULTIPLIER))


class AuthRateThrottle(SimpleRateThrottle):
    """Throttle con tasas como ``"5/15m"`` y clave por IP más correo normalizado. Es la
    base de todos los límites de la API (también el de reportes)."""

    scope: str

    def get_rate(self) -> str:
        return str(settings.AUTH_RATE_LIMITS[self.scope])

    def parse_rate(self, rate: str | None) -> tuple[int, int]:
        assert rate is not None
        num, period = rate.split("/")
        multiplier = int(period[:-1] or 1)
        return int(num) * rate_multiplier(), multiplier * _PERIODS[period[-1]]

    def _hashed(self, value: str) -> str:
        # La clave de caché no guarda el correo en claro.
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _key(self, ident: str) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self._hashed(ident)}

    def _email_from_body(self, request: Request) -> str:
        data: Any = request.data
        email = data.get("email") if hasattr(data, "get") else None
        return UserManager.normalize_email(email if isinstance(email, str) else "")

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        return self._key(f"{self.get_ident(request)}|{self._email_from_body(request)}")


class _ByIPRateThrottle(AuthRateThrottle):
    """Una IP sobre todos los correos (rociado de contraseñas, SEC-09)."""

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        return self._key(self.get_ident(request))


class _ByAccountRateThrottle(AuthRateThrottle):
    """Un correo sobre todas las IP (fuerza bruta distribuida, SEC-09). Es el control
    "progresivo" de REQUERIMIENTOS §9.3: sin ``sleep``, que bloquearía los workers. Sin
    correo en el cuerpo no cuenta (ya lo cuenta el límite por IP)."""

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        email = self._email_from_body(request)
        return self._key(email) if email else None


class LoginRateThrottle(AuthRateThrottle):
    scope = "login"


class LoginIPRateThrottle(_ByIPRateThrottle):
    scope = "login_ip"


class LoginAccountRateThrottle(_ByAccountRateThrottle):
    scope = "login_account"


class PasswordResetRequestRateThrottle(AuthRateThrottle):
    scope = "password_reset_request"


class PasswordResetRequestIPRateThrottle(_ByIPRateThrottle):
    scope = "password_reset_request_ip"


class PasswordResetRequestAccountRateThrottle(_ByAccountRateThrottle):
    scope = "password_reset_request_account"


class PasswordResetConfirmRateThrottle(_ByIPRateThrottle):
    scope = "password_reset_confirm"


class AdminLoginRateThrottle(_ByIPRateThrottle):
    """Login de ``/admin/`` por IP (SEC-18). Lo usa ``config.views.admin_login`` con la
    petición de Django: ``get_ident`` solo lee ``META``."""

    scope = "admin_login"


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


class BuyerAccessIssueRateThrottle(AuthRateThrottle):
    """Emisión de enlaces del comprador: por emisor y solicitud (REQUERIMIENTOS §9.3).

    Solo cuenta los ``POST``: listar los enlaces de la solicitud no consume el límite.
    """

    scope = "buyer_access_issue"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        user_id = getattr(request.user, "pk", None)
        if request.method != "POST" or user_id is None:
            return None
        return self._key(f"{user_id}|{view.kwargs.get('application_id')}")


class BuyerAccessConsumeRateThrottle(PasswordResetConfirmRateThrottle):
    """Limita por IP los intentos de adivinar tokens de enlace del comprador."""

    scope = "buyer_access_consume"


class BuyerDocumentUploadRateThrottle(AuthRateThrottle):
    """Cargas de documentos del comprador: por sesión y solicitud (decisión 12)."""

    scope = "buyer_document_upload"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        session = request.auth
        if request.method != "POST" or not isinstance(session, BuyerSession):
            return None
        return self._key(f"{session.pk}|{session.application_id}")


def actor_ident(request: Request) -> str | None:
    """Quién consume el cupo: la sesión del comprador o el usuario interno; ``None`` si
    la petición no trae sesión."""
    session = request.auth
    if isinstance(session, BuyerSession):
        return f"buyer_session|{session.pk}"
    user_id = getattr(request.user, "pk", None)
    return None if user_id is None else f"user|{user_id}"


class DocumentDownloadRateThrottle(AuthRateThrottle):
    """Descargas de documentos: por usuario interno o por sesión del comprador
    (decisión 12). Solo cuenta las descargas, no las demás lecturas."""

    scope = "document_download"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        ident = actor_ident(request)
        return None if ident is None else self._key(ident)


class _GeneralRateThrottle(AuthRateThrottle):
    """Límite general (SEC-10): por usuario interno o sesión del comprador; sin sesión,
    por IP."""

    reads: bool

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        if (request.method in READ_METHODS) != self.reads:
            return None
        return self._key(actor_ident(request) or f"ip|{self.get_ident(request)}")


class GeneralReadRateThrottle(_GeneralRateThrottle):
    scope = "general_read"
    reads = True


class GeneralWriteRateThrottle(_GeneralRateThrottle):
    scope = "general_write"
    reads = False


class ScopedUserRateThrottle(_GeneralRateThrottle):
    """Como ``ScopedRateThrottle`` de DRF: solo actúa en las vistas que declaran
    ``throttle_scope`` (cambios de estado, radicaciones y desistimientos comparten
    ``"state_changes"``), y solo en escrituras. La tasa sale de ``AUTH_RATE_LIMITS``."""

    reads = False

    def __init__(self) -> None:
        # La tasa depende de la vista: se lee en `allow_request`.
        pass

    def allow_request(self, request: Request, view: Any) -> bool:
        scope = getattr(view, "throttle_scope", None)
        if not scope:
            return True
        self.scope = scope
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


# Los límites de toda vista. `DEFAULT_THROTTLE_CLASSES` (base.py) es esta misma lista.
GENERAL_THROTTLES: list[type[BaseThrottle]] = [
    GeneralReadRateThrottle,
    GeneralWriteRateThrottle,
    ScopedUserRateThrottle,
]
