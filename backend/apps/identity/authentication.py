from typing import Any

from django.http import HttpRequest
from rest_framework.authentication import BaseAuthentication, CSRFCheck
from rest_framework.request import Request

from apps.identity.cookies import access_cookie_name
from apps.identity.exceptions import CsrfFailed, SessionExpired
from apps.identity.models import AuthSession, User
from apps.identity.tokens import AccessTokenClaims, InvalidAccessToken, decode_access_token


def enforce_csrf(request: Request | HttpRequest) -> None:
    """Valida el token CSRF de las escrituras autenticadas por cookie.

    Es la misma comprobación que usa ``SessionAuthentication`` de DRF. Los métodos
    seguros (GET, HEAD, OPTIONS) no se validan.
    """

    def dummy_get_response(_: HttpRequest) -> None:  # pragma: no cover
        return None

    check = CSRFCheck(dummy_get_response)  # type: ignore[arg-type]
    check.process_request(request)
    reason = check.process_view(request, None, (), {})  # type: ignore[arg-type]
    if reason:
        raise CsrfFailed()


class CookieJWTAuthentication(BaseAuthentication):
    """Autentica usuarios internos con el JWT de la cookie de acceso.

    Además de validar firma, ``iss``, ``aud``, ``exp``, ``nbf`` y ``jti``, comprueba
    en cada petición que la sesión (``sid``) siga activa y que el usuario pueda
    autenticarse. Así, cerrar sesión o desactivar un usuario corta el acceso de
    inmediato, sin esperar a que venza el JWT.
    """

    def authenticate(self, request: Request) -> tuple[User, AccessTokenClaims] | None:
        raw_token = request.COOKIES.get(access_cookie_name())
        if not raw_token:
            return None

        try:
            claims = decode_access_token(raw_token)
        except InvalidAccessToken as exc:
            raise SessionExpired() from exc

        session = (
            AuthSession.objects.select_related("user")
            .filter(id=claims.session_id, user_id=claims.user_id)
            .first()
        )
        if session is None or not session.is_active_at() or not session.user.can_authenticate:
            raise SessionExpired()

        enforce_csrf(request)

        # Disponible para las vistas que necesitan la sesión actual (logout, cambio de clave).
        request.auth_session = session  # type: ignore[attr-defined]
        return session.user, claims

    def authenticate_header(self, request: Any) -> str:
        # Sin esta cabecera, DRF convertiría los 401 en 403.
        return 'Cookie realm="api"'
