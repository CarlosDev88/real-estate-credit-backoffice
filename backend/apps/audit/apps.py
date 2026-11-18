from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Auditoría"

    def ready(self) -> None:
        # Conecta los suscriptores de las señales de los demás módulos.
        from apps.audit import receivers  # noqa: F401
