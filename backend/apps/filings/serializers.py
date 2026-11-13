from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.applications.serializers import BankProductRefSerializer
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.models import CatalogItem
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.serializers import UserRefSerializer
from apps.documents.models import FileObject
from apps.filings import responses
from apps.filings.models import (
    Filing,
    FilingDocumentSnapshot,
    FilingResponse,
    FilingResponseObservation,
    FilingStatus,
)
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


# --- Respuestas del banco ---------------------------------------------------------------

MESSAGE_MAX_LENGTH = 2000
INTERNAL_COMMENT_MAX_LENGTH = 4000


def _optional_text(max_length: int, help_text: str = "") -> serializers.CharField:
    return serializers.CharField(
        max_length=max_length,
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text=help_text,
    )


def _optional_int(min_value: int, help_text: str) -> serializers.IntegerField:
    return serializers.IntegerField(
        min_value=min_value, required=False, allow_null=True, default=None, help_text=help_text
    )


class ObservationInputSerializer(StrictSerializer):
    document_slot_id = serializers.UUIDField(
        help_text="Documento observado: de esta solicitud, vigente y con una versión cargada."
    )
    reason_code = CatalogItemCodeField(
        catalog_code="document_rejection_reason",
        help_text="Motivo que ve el comprador (catálogo `document_rejection_reason`).",
    )
    message = serializers.CharField(
        max_length=MESSAGE_MAX_LENGTH, help_text="Qué debe corregir el comprador; lo ve tal cual."
    )


class FilingResponseCreateSerializer(StrictSerializer):
    """``POST /filings/{id}/responses``. Los obligatorios y los campos que admite cada
    tipo están en la descripción del endpoint; los demás responden ``400``."""

    response_type = CatalogItemCodeField(
        catalog_code=responses.RESPONSE_TYPE_CATALOG,
        help_text="`RECEIVED`, `IN_ANALYSIS`, `RETURNED`, `APPROVED`, `REJECTED`, "
        "`DISBURSED` u `OTHER` (catálogo `filing_response_type`).",
    )
    received_at = serializers.DateTimeField(
        help_text="Cuándo respondió el banco: no futura y no anterior a la radicación."
    )
    external_reference = _optional_text(REFERENCE_MAX_LENGTH)
    reason_code = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text="`RETURNED`: catálogo `filing_return_reason`. `REJECTED`: catálogo "
        "`filing_rejection_reason`.",
    )
    public_message = _optional_text(
        MESSAGE_MAX_LENGTH,
        "Lo ve el comprador. Obligatorio en `RETURNED`, `APPROVED` y `REJECTED`.",
    )
    internal_comment = _optional_text(
        INTERNAL_COMMENT_MAX_LENGTH,
        "Texto completo del banco o nota del asesor; nunca sale hacia el comprador ni el "
        "broker. Obligatorio en `OTHER`.",
    )
    observations = ObservationInputSerializer(
        many=True,
        required=False,
        default=list,
        help_text="Solo `RETURNED`, al menos una: los documentos que el banco observó.",
    )
    approved_amount_cop = _optional_int(1, "Solo `APPROVED` (obligatorio).")
    approved_term_months = _optional_int(1, "Solo `APPROVED` (obligatorio).")
    valid_until = serializers.DateField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Solo `APPROVED` (opcional): vigencia de la aprobación.",
    )
    disbursed_amount_cop = _optional_int(1, "Solo `DISBURSED` (obligatorio).")
    corrects_response_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Corrige la última respuesta de la radicación, del mismo tipo, si es "
        "`RECEIVED`, `IN_ANALYSIS` u `OTHER`. No cambia ningún estado.",
    )
    expected_version = serializers.IntegerField(
        min_value=1, help_text="Versión de la solicitud que se consultó (`ETag`)."
    )

    def validate_received_at(self, value: Any) -> Any:
        if value > timezone.now():
            raise serializers.ValidationError("La fecha de la respuesta no puede ser futura.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        for name in ("external_reference", "reason_code", "public_message", "internal_comment"):
            attrs[name] = _blank_to_none(attrs.get(name))
        code = attrs["response_type"].code
        errors = responses.field_errors(code, attrs)
        catalog = responses.RULES[code].reason_catalog
        attrs["reason"] = None
        if catalog and attrs["reason_code"] and "reason_code" not in errors:
            reason = CatalogItem.objects.filter(
                catalog__code=catalog, code=attrs["reason_code"]
            ).first()
            if reason is None or not reason.is_available_on(timezone.localdate()):
                errors["reason_code"] = [
                    f"El código «{attrs['reason_code']}» no está activo en el catálogo {catalog}."
                ]
            attrs["reason"] = reason
        valid_until = attrs.get("valid_until")
        received_on = timezone.localtime(attrs["received_at"]).date()
        if valid_until is not None and valid_until < received_on:
            errors["valid_until"] = ["No puede ser anterior a la fecha de la respuesta."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def to_input(self) -> responses.ResponseInput:
        data = self.validated_data
        return responses.ResponseInput(
            response_type=data["response_type"],
            received_at=data["received_at"],
            external_reference=data["external_reference"],
            reason=data["reason"],
            public_message=data["public_message"],
            internal_comment=data["internal_comment"],
            observations=[
                responses.Observation(
                    document_slot_id=item["document_slot_id"],
                    reason=item["reason_code"],
                    message=item["message"],
                )
                for item in data["observations"]
            ],
            approved_amount_cop=data["approved_amount_cop"],
            approved_term_months=data["approved_term_months"],
            valid_until=data["valid_until"],
            disbursed_amount_cop=data["disbursed_amount_cop"],
            corrects_response_id=data["corrects_response_id"],
        )


class EvidenceUploadSerializer(StrictSerializer):
    file = serializers.FileField(allow_empty_file=False, use_url=False)


class FilingResponseObservationSerializer(serializers.ModelSerializer):
    reason = CatalogItemRefSerializer(source="reason_item", read_only=True)
    message = serializers.CharField(source="buyer_message", read_only=True)

    class Meta:
        model = FilingResponseObservation
        fields = [
            "id",
            "document_slot_id",
            "reason",
            "message",
            "resolved_at",
            "resolved_by_file_id",
            "created_at",
        ]
        read_only_fields = fields


class EvidenceSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="original_filename", read_only=True)
    mime_type = serializers.CharField(source="detected_mime_type", read_only=True)
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = FileObject
        fields = ["filename", "mime_type", "size_bytes", "scan_status", "scanned_at", "uploaded_at"]
        read_only_fields = fields


# Lo que ve el broker de una respuesta; el resto solo el administrador y el asesor.
PUBLIC_RESPONSE_FIELDS = (
    "id",
    "filing_id",
    "response_type",
    "response_type_label",
    "received_at",
    "public_message",
    "created_at",
)


class FilingResponseSerializer(serializers.ModelSerializer):
    """Respuesta del banco. Con ``context["restricted"]`` (el broker) solo salen
    ``PUBLIC_RESPONSE_FIELDS``. Los demás no son de solo lectura para que OpenAPI no los
    marque obligatorios."""

    filing_id = serializers.UUIDField(read_only=True)
    response_type = serializers.CharField(source="response_type_item.code", read_only=True)
    response_type_label = serializers.CharField(source="response_type_item.label", read_only=True)
    reason = CatalogItemRefSerializer(
        source="reason_item",
        allow_null=True,
        required=False,
        help_text="`filing_return_reason` o `filing_rejection_reason`.",
    )
    observations = FilingResponseObservationSerializer(many=True, required=False)
    evidence = EvidenceSerializer(
        source="evidence_file_object",
        allow_null=True,
        required=False,
        help_text="Se descarga en `/evidence/download` si `scan_status` es `CLEAN`.",
    )
    recorded_by = UserRefSerializer(required=False)
    corrects_response_id = serializers.UUIDField(allow_null=True, required=False)

    class Meta:
        model = FilingResponse
        fields = [
            "id",
            "filing_id",
            "response_type",
            "response_type_label",
            "received_at",
            "public_message",
            "external_reference",
            "reason",
            "internal_comment",
            "observations",
            "approved_amount_cop",
            "approved_term_months",
            "valid_until",
            "disbursed_amount_cop",
            "evidence",
            "recorded_by",
            "corrects_response_id",
            "created_at",
        ]
        read_only_fields = ["id", "received_at", "public_message", "created_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.context.get("restricted"):
            for name in list(self.fields):
                if name not in PUBLIC_RESPONSE_FIELDS:
                    self.fields.pop(name)


class BuyerBankUpdateSerializer(serializers.Serializer):
    """Última novedad del banco para el comprador: nunca el comentario interno."""

    response_type = serializers.CharField(source="response_type_item.code")
    response_type_label = serializers.CharField(source="response_type_item.label")
    received_at = serializers.DateTimeField()
    public_message = serializers.CharField()
