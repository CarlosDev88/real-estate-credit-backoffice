from django.apps import AppConfig


class FilingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.filings"
    label = "filings"
    verbose_name = "Radicación manual y respuestas del banco"

    def ready(self) -> None:
        # Los campos de cada tipo de respuesta salen de `RULES` (una sola fuente).
        from apps.catalogs.services import register_computed_metadata
        from apps.filings.responses import RESPONSE_TYPE_CATALOG, response_type_metadata

        register_computed_metadata(RESPONSE_TYPE_CATALOG, response_type_metadata)
