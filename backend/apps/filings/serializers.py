from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.applications.serializers import BankProductRefSerializer
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.serializers import UserRefSerializer
from apps.filings.models import Filing, FilingDocumentSnapshot, FilingStatus
from config.serializers import StrictSerializer

REFERENCE_MAX_LENGTH = 100
COMMENT_MAX_LENGTH = 2000


def _blank_to_none(value: str | None) -> str | None:
    """Sin texto se guarda como nulo, como en el esquema."""
    if value is None:
        return None
    value = value.strip()
    return value or None


# --- Entrada ----------------------------------------------------------------------------


class FilingCreateSerializer(StrictSerializer):
    """``POST /applications/{id}/filings``. Lleva ``expected_version`` en el cuerpo, como
    ``/status-transitions``, en lugar de ``If-Match``."""

    bank_product_id = serializers.UUIDField(
        help_text="Producto de la financiación de la solicitud."
    )
    package_job_id = serializers.UUIDField(
        help_text="Paquete terminado y vigente de esta solicitud, con la huella documental "
        "actual y sin radicar."
    )
    channel_code = CatalogItemCodeField(
        catalog_code="filing_channel", help_text="Canal de entrega (catálogo `filing_channel`)."
    )
    external_reference = serializers.CharField(
        max_length=REFERENCE_MAX_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text="Número o código que dio el banco. Único por producto.",
    )
    filed_at = serializers.DateTimeField(help_text="Cuándo se entregó; no puede ser futura.")
    comment = serializers.CharField(
        max_length=COMMENT_MAX_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text="Nota interna; el broker no la ve.",
    )
    expected_version = serializers.IntegerField(
        min_value=1, help_text="Versión de la solicitud que se consultó (`ETag`)."
    )

    def validate_filed_at(self, value: Any) -> Any:
        if value > timezone.now():
            raise serializers.ValidationError("La fecha de radicación no puede ser futura.")
        return value

    def validate_external_reference(self, value: str | None) -> str | None:
        return _blank_to_none(value)

    def validate_comment(self, value: str | None) -> str | None:
        return _blank_to_none(value)


class FilingUpdateSerializer(StrictSerializer):
    """``PATCH /filings/{id}``: solo la referencia del banco y el comentario. Enviar
    ``null`` o vacío los borra."""

    external_reference = serializers.CharField(
        max_length=REFERENCE_MAX_LENGTH, required=False, allow_blank=True, allow_null=True
    )
    comment = serializers.CharField(
        max_length=COMMENT_MAX_LENGTH, required=False, allow_blank=True, allow_null=True
    )

    def validate_external_reference(self, value: str | None) -> str | None:
        return _blank_to_none(value)

    def validate_comment(self, value: str | None) -> str | None:
        return _blank_to_none(value)


# --- Salida -----------------------------------------------------------------------------


class FilingSerializer(serializers.ModelSerializer):
    """Radicación. Con ``context["restricted"]`` (el broker) no sale ``comment``."""

    application_id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(choices=FilingStatus.choices, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    bank_product = BankProductRefSerializer(read_only=True)
    channel = CatalogItemRefSerializer(
        source="channel_item", read_only=True, help_text="Catálogo `filing_channel`."
    )
    package_job_id = serializers.UUIDField(read_only=True)
    filed_by = UserRefSerializer(read_only=True)
    # No es de solo lectura para que OpenAPI no lo marque obligatorio: falta para el broker.
    comment = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Nota interna. No sale para el broker.",
    )
    responses_count = serializers.IntegerField(
        read_only=True, help_text="Respuestas del banco registradas, incluidas las correcciones."
    )
    application_status = serializers.ChoiceField(
        source="application.status", choices=ApplicationStatus.choices, read_only=True
    )
    application_status_label = serializers.CharField(
        source="application.get_status_display", read_only=True
    )

    class Meta:
        model = Filing
        fields = [
            "id",
            "application_id",
            "sequence_number",
            "status",
            "status_label",
            "bank_product",
            "channel",
            "external_reference",
            "package_job_id",
            "filed_by",
            "filed_at",
            "target_response_at",
            "comment",
            "responses_count",
            "application_status",
            "application_status_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [name for name in fields if name != "comment"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.context.get("restricted"):
            self.fields.pop("comment")


class FilingDocumentSnapshotSerializer(serializers.ModelSerializer):
    """Versión exacta que se entregó al banco en la radicación."""

    slot_id = serializers.UUIDField(source="document_file.slot_id", read_only=True)
    document_file_id = serializers.UUIDField(read_only=True)
    version_number = serializers.IntegerField(source="document_file.version_number", read_only=True)
    client_filename = serializers.CharField(source="document_file.client_filename", read_only=True)
    mime_type = serializers.CharField(source="file_object.detected_mime_type", read_only=True)
    size_bytes = serializers.IntegerField(source="file_object.size_bytes", read_only=True)

    class Meta:
        model = FilingDocumentSnapshot
        fields = [
            "id",
            "slot_id",
            "document_file_id",
            "version_number",
            "document_type_code",
            "client_filename",
            "mime_type",
            "size_bytes",
            "sha256",
            "created_at",
        ]
        read_only_fields = fields
