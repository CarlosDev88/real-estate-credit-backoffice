from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documentos: configuración y expediente"

    def ready(self) -> None:
        # El almacenamiento en memoria y el antivirus falso solo valen en desarrollo o
        # pruebas: con cualquier otra configuración, el proceso no arranca.
        from apps.documents.scanning import validate_scanner_settings
        from apps.documents.storage import validate_storage_settings

        validate_storage_settings()
        validate_scanner_settings()
