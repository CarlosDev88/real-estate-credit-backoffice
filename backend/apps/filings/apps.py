from django.apps import AppConfig


class FilingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.filings"
    label = "filings"
    verbose_name = "Radicación manual y respuestas del banco"
