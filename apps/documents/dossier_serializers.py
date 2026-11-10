"""Respuestas internas del expediente documental (API §19). Nunca exponen
``object_key`` ni el bucket del archivo."""

from rest_framework import serializers

from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.serializers import UserRefSerializer
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentReview,
    FileObject,
)
from apps.documents.serializers import DocumentTypeRefSerializer


def slot_label(slot: ApplicationDocumentSlot) -> str:
    """Etiqueta del slot: "Desprendible de nómina 2 de 3", o solo el nombre del tipo.

    El total son los slots vigentes del juego (``set_size``). Un slot retirado usa su
    snapshot de ``minimum_files``.
    """
    name = slot.document_type.name
    total = slot.minimum_files if slot.retired_at is not None else getattr(slot, "set_size", None)
    total = total or slot.minimum_files
    return name if total <= 1 else f"{name} {slot.slot_index} de {total}"


class SlotDocumentTypeSerializer(DocumentTypeRefSerializer):
    holder_scope = serializers.CharField()
    allowed_mime_types = serializers.ListField(child=serializers.CharField())
    max_size_bytes = serializers.IntegerField()


class SlotParticipantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    client_id = serializers.UUIDField()
    full_name = serializers.CharField(source="client.full_name")
    is_active = serializers.BooleanField()


class CurrentFileSerializer(serializers.ModelSerializer):
    scan_status = serializers.CharField(source="file_object.scan_status")

    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "version_number",
            "status",
            "client_filename",
            "document_date",
            "expires_at",
            "scan_status",
            "created_at",
        ]
        read_only_fields = fields


class DocumentSlotSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(read_only=True)
    participant = SlotParticipantSerializer(read_only=True, allow_null=True)
    document_type = SlotDocumentTypeSerializer(read_only=True)
    # `label` choca con el atributo `Field.label` de los stubs de DRF; como en
    # `CatalogItemRefSerializer`, el campo de la API se llama así.
    label = serializers.SerializerMethodField()  # type: ignore[assignment]
    requirement_id = serializers.UUIDField(read_only=True, allow_null=True)
    waiver_reason = CatalogItemRefSerializer(
        source="waiver_reason_item", read_only=True, allow_null=True
    )
    current_file = CurrentFileSerializer(read_only=True, allow_null=True)
    is_retired = serializers.BooleanField(read_only=True)

    class Meta:
        model = ApplicationDocumentSlot
        fields = [
            "id",
            "application_id",
            "participant",
            "document_type",
            "label",
            "slot_index",
            "requirement_id",
            "requirement_version",
            "is_required",
            "is_waivable",
            "minimum_files",
            "alternative_group_code",
            "validity_days",
            "sort_order",
            "status",
            "waiver_reason",
            "current_file",
            "locked_at",
            "is_retired",
            "retired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_label(self, obj: ApplicationDocumentSlot) -> str:
        return slot_label(obj)


class FileMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileObject
        fields = [
            "id",
            "detected_mime_type",
            "size_bytes",
            "sha256",
            "scan_status",
            "scanned_at",
        ]
        read_only_fields = fields


class DocumentReviewSerializer(serializers.ModelSerializer):
    reason = CatalogItemRefSerializer(source="reason_item", read_only=True, allow_null=True)
    reviewer = UserRefSerializer(read_only=True)

    class Meta:
        model = DocumentReview
        fields = [
            "id",
            "decision",
            "reason",
            "buyer_comment",
            "internal_comment",
            "reviewer",
            "created_at",
        ]
        read_only_fields = fields


class DocumentFileSerializer(serializers.ModelSerializer):
    """Versión cargada. ``reviews`` va de la más reciente a la primera: una corrección
    es una fila nueva."""

    slot_id = serializers.UUIDField(read_only=True)
    uploaded_by_buyer_session_id = serializers.UUIDField(read_only=True)
    is_current = serializers.SerializerMethodField()
    file = FileMetadataSerializer(source="file_object", read_only=True)
    reviews = DocumentReviewSerializer(many=True, read_only=True)

    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "slot_id",
            "version_number",
            "status",
            "is_current",
            "client_filename",
            "document_date",
            "expires_at",
            "uploaded_by_buyer_session_id",
            "file",
            "reviews",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_current(self, obj: DocumentFile) -> bool:
        return bool(obj.pk == self.context.get("current_file_id"))


class SlotRefreshSerializer(serializers.Serializer):
    """Lista vigente después del recálculo y los ids de lo que cambió."""

    created = serializers.ListField(child=serializers.UUIDField())
    retired = serializers.ListField(child=serializers.UUIDField())
    revived = serializers.ListField(child=serializers.UUIDField())
    updated = serializers.ListField(child=serializers.UUIDField())
    slots = DocumentSlotSerializer(many=True)
