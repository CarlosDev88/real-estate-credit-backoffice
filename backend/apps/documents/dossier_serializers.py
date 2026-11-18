"""Respuestas internas del expediente documental (API §19). Nunca exponen
``object_key`` ni el bucket del archivo."""

from datetime import date
from typing import Any

from django.db import models
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.serializers import UserRefSerializer
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentReview,
    FileObject,
    HolderScope,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.documents.models.review import FILE_DECISIONS
from apps.documents.serializers import DocumentTypeRefSerializer
from config.serializers import ChoiceLabelField, StrictSerializer


def slot_label(slot: ApplicationDocumentSlot, set_size: int | None = None) -> str:
    """Etiqueta del slot: "Desprendible de nómina 2 de 3", o solo el nombre del tipo.

    El total son los slots vigentes del juego (``set_size``, o la anotación del mismo
    nombre). Un slot retirado usa su snapshot de ``minimum_files``.
    """
    name = slot.document_type.name
    if set_size is None:
        set_size = getattr(slot, "set_size", None)
    total = slot.minimum_files if slot.retired_at is not None else set_size
    total = total or slot.minimum_files
    return name if total <= 1 else f"{name} {slot.slot_index} de {total}"


class SlotDocumentTypeSerializer(DocumentTypeRefSerializer):
    holder_scope = serializers.CharField()
    holder_scope_label = ChoiceLabelField(HolderScope, source="holder_scope")
    allowed_mime_types = serializers.ListField(child=serializers.CharField())
    max_size_bytes = serializers.IntegerField()


class SlotParticipantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    role_label = serializers.CharField(source="get_role_display")
    client_id = serializers.UUIDField()
    full_name = serializers.CharField(source="client.full_name")
    is_active = serializers.BooleanField()


class UploaderType(models.TextChoices):
    BUYER = "buyer", "Comprador"
    USER = "user", "Usuario interno"


class UploadedBySerializer(serializers.Serializer):
    """Quién cargó la versión. Nunca el correo ni el documento."""

    type = serializers.ChoiceField(choices=UploaderType.choices)
    name = serializers.CharField(
        help_text='"Comprador" para el comprador; el nombre del usuario interno.'
    )


def uploaded_by(version: DocumentFile) -> dict[str, str]:
    """Hoy solo el comprador carga (``uploaded_by_buyer_session`` es obligatoria)."""
    if version.uploaded_by_buyer_session_id is not None:
        return {"type": UploaderType.BUYER.value, "name": str(UploaderType.BUYER.label)}
    user = getattr(version, "uploaded_by_user", None)
    return {"type": UploaderType.USER.value, "name": user.get_full_name() if user else ""}


class CurrentFileSerializer(serializers.ModelSerializer):
    """Versión vigente del slot. ``context["last_buyer_comment"]`` trae el comentario."""

    status_label = ChoiceLabelField(DocumentFileStatus, source="status")
    scan_status_label = ChoiceLabelField(ScanStatus, source="file_object.scan_status")
    scan_status = serializers.CharField(source="file_object.scan_status")
    size_bytes = serializers.IntegerField(source="file_object.size_bytes")
    detected_mime_type = serializers.CharField(source="file_object.detected_mime_type")
    last_buyer_comment = serializers.SerializerMethodField(
        help_text="Mensaje al comprador de la última aprobación o rechazo de esta versión; "
        "nulo si no hay o va vacío."
    )

    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "version_number",
            "status",
            "status_label",
            "client_filename",
            "document_date",
            "expires_at",
            "scan_status",
            "scan_status_label",
            "size_bytes",
            "detected_mime_type",
            "last_buyer_comment",
            "created_at",
        ]
        read_only_fields = fields

    def get_last_buyer_comment(self, obj: DocumentFile) -> str | None:
        return self.context.get("last_buyer_comment") or None


_NOT_ANNOTATED = object()


def _last_buyer_comment(slot: ApplicationDocumentSlot) -> str | None:
    """La anotación de ``dossier.slots_queryset``; sin ella, se consulta."""
    value = getattr(slot, "last_buyer_comment", _NOT_ANNOTATED)
    if value is _NOT_ANNOTATED:
        value = (
            DocumentReview.objects.filter(
                document_file_id=slot.current_file_id, decision__in=FILE_DECISIONS
            )
            .order_by("-created_at")
            .values_list("buyer_comment", flat=True)
            .first()
        )
    return value or None  # type: ignore[return-value]


class DocumentSlotSerializer(serializers.ModelSerializer):
    status_label = ChoiceLabelField(SlotStatus, source="status")
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
    current_file = serializers.SerializerMethodField()
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
            "status_label",
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

    @extend_schema_field(CurrentFileSerializer(allow_null=True))
    def get_current_file(self, obj: ApplicationDocumentSlot) -> dict[str, Any] | None:
        version = obj.current_file
        if version is None:
            return None
        context = {"last_buyer_comment": _last_buyer_comment(obj)}
        return dict(CurrentFileSerializer(version, context=context).data)


class FileMetadataSerializer(serializers.ModelSerializer):
    scan_status_label = ChoiceLabelField(ScanStatus, source="scan_status")

    class Meta:
        model = FileObject
        fields = [
            "id",
            "detected_mime_type",
            "size_bytes",
            "sha256",
            "scan_status",
            "scan_status_label",
            "scanned_at",
        ]
        read_only_fields = fields


class DocumentReviewSerializer(serializers.ModelSerializer):
    decision_label = ChoiceLabelField(ReviewDecision, source="decision")
    reason = CatalogItemRefSerializer(source="reason_item", read_only=True, allow_null=True)
    reviewer = UserRefSerializer(read_only=True)

    class Meta:
        model = DocumentReview
        fields = [
            "id",
            "decision",
            "decision_label",
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

    status_label = ChoiceLabelField(DocumentFileStatus, source="status")
    slot_id = serializers.UUIDField(read_only=True)
    uploaded_by_buyer_session_id = serializers.UUIDField(read_only=True)
    uploaded_by = serializers.SerializerMethodField()
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
            "status_label",
            "is_current",
            "client_filename",
            "document_date",
            "expires_at",
            "uploaded_by_buyer_session_id",
            "uploaded_by",
            "file",
            "reviews",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(UploadedBySerializer)
    def get_uploaded_by(self, obj: DocumentFile) -> dict[str, str]:
        return uploaded_by(obj)

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

    decision_label = ChoiceLabelField(ReviewDecision, source="decision")
    reason = CatalogItemRefSerializer(source="reason_item", read_only=True, allow_null=True)
    reviewer = UserRefSerializer(read_only=True)
    document_file_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DocumentReview
        fields = [
            "id",
            "decision",
            "decision_label",
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

    status_label = ChoiceLabelField(DocumentFileStatus, source="status")
    scan_status_label = ChoiceLabelField(ScanStatus, source="file_object.scan_status")
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
            "status_label",
            "scan_status",
            "scan_status_label",
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
