from django.apps import AppConfig


class CatalogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalogs"
    label = "catalogs"
    verbose_name = "Catálogos y flujos"

    def ready(self) -> None:
        # Registra la extensión de OpenAPI de CatalogItemCodeField.
        from apps.catalogs import schema  # noqa: F401
