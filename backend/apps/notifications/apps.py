from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Notificaciones"

    def ready(self) -> None:
        # Conecta los suscriptores a los eventos de dominio.
        from apps.notifications import receivers  # noqa: F401
