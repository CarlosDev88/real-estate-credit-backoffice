from django.apps import AppConfig


class ActivityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.activity"
    label = "activity"
    verbose_name = "Actividad"

    def ready(self) -> None:
        # Conecta los suscriptores de las señales de los demás módulos.
        from apps.activity import receivers  # noqa: F401
