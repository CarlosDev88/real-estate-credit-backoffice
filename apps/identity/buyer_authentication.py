"""Autenticación del portal del comprador (API §4.1 y §8).

Está separada de ``authentication.py`` porque depende de ``applications``, y DRF
importa ``authentication.py`` al cargar su configuración.

- Solo la usan las vistas ``/buyer/*``. Esas vistas no aceptan el JWT interno, y la
  cookie del comprador no autentica ningún endpoint interno.
- ``request.user`` sigue siendo ``AnonymousUser``; la sesión queda en ``request.auth``.
"""

from typing import Any

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from apps.identity.authentication import enforce_csrf
from apps.identity.buyer_sessions import find_active_session, touch_session
from apps.identity.consents import ensure_consents_accepted
from apps.identity.cookies import buyer_session_cookie_name
from apps.identity.exceptions import BuyerSessionExpired
from apps.identity.models import BuyerSession


class BuyerSessionAuthentication(BaseAuthentication):
    """Autentica al comprador con la cookie de su sesión temporal.

    - Sin cookie: no autentica, y la vista responde ``401 NOT_AUTHENTICATED``.
    - Sesión desconocida, vencida o revocada, o cliente que dejó de ser el titular
      activo: ``401 SESSION_EXPIRED``.
    - Las escrituras exigen el token CSRF.
    """

    def authenticate(self, request: Request) -> tuple[AnonymousUser, BuyerSession] | None:
        raw_token = request.COOKIES.get(buyer_session_cookie_name())
        if not raw_token:
            return None
        session = find_active_session(raw_token)
        if session is None:
            raise BuyerSessionExpired()
        enforce_csrf(request)
        touch_session(session)
        return AnonymousUser(), session

    def authenticate_header(self, request: Any) -> str:
        # Sin esta cabecera, DRF convertiría los 401 en 403.
        return 'Cookie realm="buyer"'


class IsBuyerSession(BasePermission):
    """La petición viene con una sesión del comprador válida."""

    def has_permission(self, request: Request, view: Any) -> bool:
        return isinstance(request.auth, BuyerSession)


class ConsentsAccepted(BasePermission):
    """Bloquea las escrituras del portal mientras falte un consentimiento obligatorio.

    Responde ``403 CONSENT_REQUIRED``. Las lecturas siguen permitidas, y las vistas de
    consentimientos y el logout no usan este permiso. Va después de ``IsBuyerSession``.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        session = request.auth
        if isinstance(session, BuyerSession):
            ensure_consents_accepted(session)
        return True
