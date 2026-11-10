"""Respuestas internas del expediente documental (API §19). Nunca exponen
``object_key`` ni el bucket del archivo."""

from datetime import date
from typing import Any

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.serializers import UserRefSerializer
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentReview,
    FileObject,
    ReviewDecision,
)
from apps.documents.serializers import DocumentTypeRefSerializer
from config.serializers import StrictSerializer


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


# --- Revisión (Parte 5) --------------------------------------------------------------------


class SlotDecisionSerializer(serializers.ModelSerializer):
    """Exoneración o reapertura del slot. ``decision_batch_id`` es el lote: los slots de
    un grupo alternativo exonerados juntos lo comparten."""

    reason = CatalogItemRefSerializer(source="reason_item", read_only=True, allow_null=True)
    reviewer = UserRefSerializer(read_only=True)
    document_file_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DocumentReview
        fields = [
            "id",
            "decision",
            "reason",
            "internal_comment",
            "document_file_id",
            "decision_batch_id",
            "reviewer",
            "created_at",
        ]
        read_only_fields = fields


class DocumentSlotDetailSerializer(DocumentSlotSerializer):
    """Detalle del slot con el historial de exoneraciones y reaperturas, de la más
    reciente a la primera. Las aprobaciones y los rechazos van en cada versión."""

    waiver_history = SlotDecisionSerializer(many=True, read_only=True)

    class Meta(DocumentSlotSerializer.Meta):
        fields = [*DocumentSlotSerializer.Meta.fields, "waiver_history"]
        read_only_fields = fields


def _comment_field(help_text: str) -> serializers.CharField:
    return serializers.CharField(
        required=False, allow_null=True, default=None, max_length=2000, help_text=help_text
    )


# Qué campos admite cada decisión y cuáles exige.
_DECISION_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    ReviewDecision.APPROVED: (
        {"document_file_id", "internal_comment", "document_date"},
        {"document_file_id"},
    ),
    ReviewDecision.REJECTED: (
        {"document_file_id", "reason_code", "buyer_comment", "internal_comment"},
        {"document_file_id", "reason_code", "buyer_comment"},
    ),
    ReviewDecision.WAIVED: ({"reason_code", "internal_comment"}, {"reason_code"}),
    ReviewDecision.REOPENED: ({"internal_comment"}, {"internal_comment"}),
}
_REASON_CATALOGS = {
    ReviewDecision.REJECTED: "document_rejection_reason",
    ReviewDecision.WAIVED: "document_waiver_reason",
}
_OPTIONAL_FIELDS = (
    "document_file_id",
    "reason_code",
    "buyer_comment",
    "internal_comment",
    "document_date",
)


class DocumentSlotReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=ReviewDecision.choices)
    document_file_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Versión revisada: la vigente del slot. Solo en `APPROVED` y `REJECTED`.",
    )
    reason_code = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Motivo: `document_rejection_reason` al rechazar y `document_waiver_reason` "
            "al exonerar."
        ),
    )
    buyer_comment = _comment_field("Lo que ve el comprador. Obligatorio al rechazar.")
    internal_comment = _comment_field(
        "Nota interna; nunca la ve el comprador. Obligatoria al reabrir."
    )
    document_date = serializers.DateField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Solo al aprobar: corrige la fecha de expedición o del periodo. Con ella se "
            "recalcula el vencimiento."
        ),
    )

    def validate_document_date(self, value: date | None) -> date | None:
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("La fecha del documento no puede ser futura.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        decision = attrs["decision"]
        allowed, required = _DECISION_FIELDS[decision]
        errors: dict[str, Any] = {}
        for field in _OPTIONAL_FIELDS:
            present = attrs.get(field) is not None
            if present and field not in allowed:
                errors[field] = [
                    ErrorDetail(f"No aplica a la decisión {decision}.", code="not_allowed")
                ]
            elif not present and field in required:
                errors[field] = [
                    ErrorDetail(f"Es obligatorio en la decisión {decision}.", code="required")
                ]
        if not errors and decision in _REASON_CATALOGS:
            reason_field = CatalogItemCodeField(catalog_code=_REASON_CATALOGS[decision])
            try:
                attrs["reason_item"] = reason_field.to_internal_value(attrs["reason_code"])
            except serializers.ValidationError as exc:
                errors["reason_code"] = exc.detail
        if errors:
            raise serializers.ValidationError(errors)
        attrs.pop("reason_code", None)
        return attrs


class DocumentSlotReviewResultSerializer(serializers.Serializer):
    """Slots que cambiaron con la decisión: uno al aprobar o rechazar; los del grupo al
    exonerar o reabrir."""

    slots = DocumentSlotSerializer(many=True)


class DocumentFileScanStatusSerializer(serializers.ModelSerializer):
    """Validación técnica y antivirus de una versión."""

    document_file_id = serializers.UUIDField(source="id", read_only=True)
    scan_status = serializers.CharField(source="file_object.scan_status", read_only=True)
    scanned_at = serializers.DateTimeField(
        source="file_object.scanned_at", read_only=True, allow_null=True
    )
    detected_mime_type = serializers.CharField(
        source="file_object.detected_mime_type", read_only=True
    )
    size_bytes = serializers.IntegerField(source="file_object.size_bytes", read_only=True)
    sha256 = serializers.CharField(source="file_object.sha256", read_only=True)

    class Meta:
        model = DocumentFile
        fields = [
            "document_file_id",
            "status",
            "scan_status",
            "scanned_at",
            "detected_mime_type",
            "size_bytes",
            "sha256",
        ]
        read_only_fields = fields


class DocumentDownloadSerializer(serializers.Serializer):
    """URL prefirmada de corta duración. Es una credencial: no se guarda ni se comparte."""

    url = serializers.CharField()
    expires_at = serializers.DateTimeField()
