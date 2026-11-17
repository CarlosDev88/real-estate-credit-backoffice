from django.apps import AppConfig


class IdempotencyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.idempotency"
    label = "idempotency"
    verbose_name = "Idempotencia de las operaciones críticas"
