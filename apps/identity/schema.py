"""Documenta en OpenAPI la autenticación por cookie del usuario interno."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension

from apps.identity.cookies import access_cookie_name


class CookieJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.identity.authentication.CookieJWTAuthentication"
    name = "internalSession"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": access_cookie_name(),
            "description": (
                "JWT de acceso emitido por `POST /api/v1/auth/login`. Las escrituras "
                "también requieren la cabecera `X-CSRFToken` con el valor de la cookie "
                "`app_csrf`."
            ),
        }
