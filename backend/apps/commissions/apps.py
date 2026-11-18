from django.apps import AppConfig


class CommissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.commissions"
    label = "commissions"
    verbose_name = "Comisiones"

    def ready(self) -> None:
        # Conecta el disparo automático de la liquidación (``filing_response_recorded``).
        from apps.commissions import receivers  # noqa: F401
