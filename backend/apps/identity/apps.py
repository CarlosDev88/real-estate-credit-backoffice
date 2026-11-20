from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.identity"
    label = "identity"

    def ready(self) -> None:
        # Registra la extensión de OpenAPI para la autenticación por cookie.
        # Comprobaciones de arranque de las claves (SEC-03).
        from apps.identity import (
            checks,  # noqa: F401
            schema,  # noqa: F401
        )
