"""Respuestas del expediente para el portal del comprador (decisión 2).

Llevan lo que necesita para cargar (formatos, tamaño máximo, archivos pedidos) y el
motivo y comentario del último rechazo, pero nunca el comentario interno, el revisor,
el requisito ni los metadatos técnicos del análisis.
"""

from datetime import date
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.documents.dossier_serializers import slot_label
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.documents.scans import SECURITY_REJECTION_MESSAGE
from apps.documents.uploads import upload_block
from config.serializers import StrictSerializer


class BuyerRejectionSerializer(serializers.Serializer):
    """Por qué se rechazó la versión. Sin motivo de catálogo si la rechazó el análisis
    de seguridad."""

    reason = CatalogItemRefSerializer(allow_null=True)
    buyer_comment = serializers.CharField()
    rejected_at = serializers.DateTimeField()


def version_rejection(version: DocumentFile | None) -> dict[str, Any] | None:
    """Rechazo de la versión para el comprador. Espera ``reviews`` precargadas de la más
    reciente a la primera."""
    if version is None or version.status != DocumentFileStatus.REJECTED:
        return None
    file_object = version.file_object
    if file_object.scan_status in (ScanStatus.INFECTED, ScanStatus.INVALID):
        return {
            "reason": None,
            "buyer_comment": SECURITY_REJECTION_MESSAGE,
            "rejected_at": file_object.scanned_at,
        }
    latest = next(iter(version.reviews.all()), None)
    if latest is None or latest.decision != ReviewDecision.REJECTED:
        return None
    return {
        "reason": latest.reason_item,
        "buyer_comment": latest.buyer_comment,
        "rejected_at": latest.created_at,
    }


class BuyerDocumentFileSerializer(serializers.ModelSerializer):
    """Versión cargada, vista por el comprador. ``UPLOADED`` significa que el análisis
    de seguridad sigue en curso; ``IN_REVIEW``, que espera al asesor."""

    mime_type = serializers.CharField(source="file_object.detected_mime_type", read_only=True)
    size_bytes = serializers.IntegerField(source="file_object.size_bytes", read_only=True)
    rejection = serializers.SerializerMethodField()

    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "version_number",
            "status",
            "client_filename",
            "document_date",
            "expires_at",
            "mime_type",
            "size_bytes",
            "rejection",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(BuyerRejectionSerializer(allow_null=True))
    def get_rejection(self, obj: DocumentFile) -> dict[str, Any] | None:
        rejection = version_rejection(obj)
        return None if rejection is None else dict(BuyerRejectionSerializer(rejection).data)


class BuyerDocumentVersionSerializer(BuyerDocumentFileSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta(BuyerDocumentFileSerializer.Meta):
        fields = [*BuyerDocumentFileSerializer.Meta.fields, "is_current"]
        read_only_fields = fields

    def get_is_current(self, obj: DocumentFile) -> bool:
        return bool(obj.pk == self.context.get("current_file_id"))


class BuyerSlotParticipantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    full_name = serializers.CharField(source="client.full_name")


class BuyerSlotDocumentTypeSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    holder_scope = serializers.CharField()


class BuyerDocumentSlotSerializer(serializers.ModelSerializer):
    """Documento esperado. ``participant`` es nulo en los documentos de la solicitud
    (inmueble, legalización). ``can_upload`` dice si hoy admite una carga."""

    participant = BuyerSlotParticipantSerializer(read_only=True, allow_null=True)
    document_type = BuyerSlotDocumentTypeSerializer(read_only=True)
    # `label` choca con el atributo `Field.label` de los stubs de DRF; como en
    # `CatalogItemRefSerializer`, el campo de la API se llama así.
    label = serializers.SerializerMethodField()  # type: ignore[assignment]
    allowed_mime_types = serializers.ListField(
        source="document_type.allowed_mime_types", child=serializers.CharField(), read_only=True
    )
    max_size_bytes = serializers.IntegerField(source="document_type.max_size_bytes", read_only=True)
    can_upload = serializers.SerializerMethodField()
    current_file = BuyerDocumentFileSerializer(read_only=True, allow_null=True)
    rejection = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationDocumentSlot
        fields = [
            "id",
            "participant",
            "document_type",
            "label",
            "slot_index",
            "is_required",
            "minimum_files",
            "alternative_group_code",
            "validity_days",
            "allowed_mime_types",
            "max_size_bytes",
            "status",
            "can_upload",
            "current_file",
            "rejection",
            "updated_at",
        ]
        read_only_fields = fields

    def get_label(self, obj: ApplicationDocumentSlot) -> str:
        return slot_label(obj)

    def get_can_upload(self, obj: ApplicationDocumentSlot) -> bool:
        return upload_block(self.context["application"], obj) is None

    @extend_schema_field(BuyerRejectionSerializer(allow_null=True))
    def get_rejection(self, obj: ApplicationDocumentSlot) -> dict[str, Any] | None:
        """El rechazo vigente: el de la versión actual mientras el slot esté rechazado."""
        if obj.status != SlotStatus.REJECTED:
            return None
        rejection = version_rejection(obj.current_file)
        return None if rejection is None else dict(BuyerRejectionSerializer(rejection).data)


class BuyerDocumentUploadSerializer(StrictSerializer):
    file = serializers.FileField(allow_empty_file=False, use_url=False)
    document_date = serializers.DateField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Fecha de expedición o del periodo del documento. Con ella se calcula su "
            "vencimiento si el documento tiene vigencia."
        ),
    )

    def validate_document_date(self, value: date | None) -> date | None:
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("La fecha del documento no puede ser futura.")
        return value
