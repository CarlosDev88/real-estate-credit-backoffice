from typing import Any

from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.banking.models import BankProduct
from apps.banking.serializers import RuleProductRefSerializer
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.documents.constants import ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from apps.documents.models import (
    DocumentRequirement,
    DocumentType,
    HolderScope,
    ParticipantRole,
)
from config.serializers import StrictSerializer

MAX_VALIDITY_DAYS = 3650  # 10 años; cabe en SMALLINT.
MAX_MINIMUM_FILES = 24
MAX_SORT_ORDER = 100_000
MAX_PREVIEW_PARTICIPANTS = 10

document_type_code_validator = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,79}$",
    "Usa mayúsculas, números y guion bajo, empezando por una letra (ej. PAYROLL_SLIP).",
)
group_code_validator = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,49}$",
    "Usa mayúsculas, números y guion bajo, empezando por una letra (ej. INCOME_TAX_PROOF).",
)


def _validity_days_field(**kwargs: Any) -> serializers.IntegerField:
    return serializers.IntegerField(min_value=1, max_value=MAX_VALIDITY_DAYS, **kwargs)


# --- Tipos documentales -----------------------------------------------------------------


class DocumentTypeSerializer(serializers.ModelSerializer):
    allowed_mime_types = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = DocumentType
        fields = [
            "id",
            "code",
            "name",
            "description",
            "allowed_mime_types",
            "max_size_bytes",
            "default_validity_days",
            "is_repeatable",
            "holder_scope",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DocumentTypeRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


def _mime_types_field(**kwargs: Any) -> serializers.ListField:
    return serializers.ListField(
        child=serializers.ChoiceField(choices=list(ALLOWED_MIME_TYPES)),
        min_length=1,
        max_length=len(ALLOWED_MIME_TYPES),
        help_text=f"Subconjunto de: {', '.join(ALLOWED_MIME_TYPES)}.",
        **kwargs,
    )


def _max_size_field(**kwargs: Any) -> serializers.IntegerField:
    return serializers.IntegerField(
        min_value=1,
        max_value=MAX_FILE_SIZE_BYTES,
        help_text=f"Bytes. Máximo {MAX_FILE_SIZE_BYTES} (10 MB).",
        **kwargs,
    )


def _holder_scope_field(**kwargs: Any) -> serializers.ChoiceField:
    return serializers.ChoiceField(
        choices=HolderScope.choices,
        help_text=(
            "`PARTICIPANT`: se pide a cada participante al que aplique el requisito. "
            "`APPLICATION`: se pide una sola vez por solicitud (inmueble, legalización)."
        ),
        **kwargs,
    )


class _DocumentTypeFields(StrictSerializer):
    def validate_allowed_mime_types(self, value: list[str]) -> list[str]:
        duplicated = sorted({mime for mime in value if value.count(mime) > 1})
        if duplicated:
            raise serializers.ValidationError(f"Formatos repetidos: {', '.join(duplicated)}.")
        return value


class DocumentTypeCreateSerializer(_DocumentTypeFields):
    code = serializers.CharField(max_length=80, validators=[document_type_code_validator])
    name = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    allowed_mime_types = _mime_types_field()
    max_size_bytes = _max_size_field()
    default_validity_days = _validity_days_field(required=False, allow_null=True, default=None)
    is_repeatable = serializers.BooleanField(required=False, default=False)
    holder_scope = _holder_scope_field(required=False, default=HolderScope.PARTICIPANT)


class DocumentTypeUpdateSerializer(_DocumentTypeFields):
    """El código no se edita: es estable. El estado cambia con activate/deactivate."""

    name = serializers.CharField(max_length=180, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    allowed_mime_types = _mime_types_field(required=False)
    max_size_bytes = _max_size_field(required=False)
    default_validity_days = _validity_days_field(required=False, allow_null=True)
    is_repeatable = serializers.BooleanField(required=False)
    holder_scope = _holder_scope_field(required=False)


# --- Requisitos -------------------------------------------------------------------------


class DocumentRequirementSerializer(serializers.ModelSerializer):
    bank_product = RuleProductRefSerializer(read_only=True, allow_null=True)
    document_type = DocumentTypeRefSerializer(read_only=True)
    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True, allow_null=True)
    employment_profile = CatalogItemRefSerializer(
        source="employment_profile_item", read_only=True, allow_null=True
    )
    property_condition = CatalogItemRefSerializer(
        source="property_condition_item", read_only=True, allow_null=True
    )

    class Meta:
        model = DocumentRequirement
        fields = [
            "id",
            "bank_product",
            "document_type",
            "purpose",
            "employment_profile",
            "participant_role",
            "property_condition",
            "version",
            "is_required",
            "is_waivable",
            "minimum_files",
            "alternative_group_code",
            "validity_days",
            "sort_order",
            "status",
            "valid_from",
            "valid_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


def _bank_product(value: Any) -> BankProduct:
    product = BankProduct.objects.select_related("bank").filter(pk=value).first()
    if product is None:
        raise serializers.ValidationError("El producto no existe.")
    return product


class _RequirementFields(StrictSerializer):
    # Nombre en la API → nombre en el modelo.
    _RENAMES = {
        "bank_product_id": "bank_product",
        "document_type_id": "document_type",
        "purpose_code": "purpose_item",
        "employment_profile_code": "employment_profile_item",
        "property_condition_code": "property_condition_item",
    }

    def validate_alternative_group_code(self, value: str | None) -> str | None:
        return value or None

    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        for api_name, model_name in self._RENAMES.items():
            if api_name in data:
                data[model_name] = data.pop(api_name)
        return data


def _group_code_field(**kwargs: Any) -> serializers.CharField:
    return serializers.CharField(
        max_length=50,
        allow_null=True,
        allow_blank=True,
        validators=[group_code_validator],
        help_text="Requisitos del mismo alcance con el mismo código: basta uno de ellos.",
        **kwargs,
    )


class DocumentRequirementCreateSerializer(_RequirementFields):
    bank_product_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Vacío: requisito general, aplica a todos los productos.",
    )
    document_type_id = serializers.UUIDField()
    purpose_code = CatalogItemCodeField(
        catalog_code="loan_purpose", required=False, allow_null=True, default=None
    )
    employment_profile_code = CatalogItemCodeField(
        catalog_code="employment_profile", required=False, allow_null=True, default=None
    )
    participant_role = serializers.ChoiceField(
        choices=ParticipantRole.choices,
        required=False,
        allow_null=True,
        default=None,
        help_text="Vacío: aplica a todos los participantes.",
    )
    property_condition_code = CatalogItemCodeField(
        catalog_code="property_condition", required=False, allow_null=True, default=None
    )
    is_required = serializers.BooleanField(required=False, default=True)
    is_waivable = serializers.BooleanField(required=False, default=False)
    minimum_files = serializers.IntegerField(
        min_value=1, max_value=MAX_MINIMUM_FILES, required=False, default=1
    )
    alternative_group_code = _group_code_field(required=False, default=None)
    validity_days = _validity_days_field(
        required=False,
        allow_null=True,
        default=None,
        help_text="Vacío: usa la vigencia sugerida por el tipo.",
    )
    sort_order = serializers.IntegerField(
        min_value=0, max_value=MAX_SORT_ORDER, required=False, default=0
    )
    valid_from = serializers.DateTimeField(required=False, help_text="Por defecto, ahora.")
    valid_to = serializers.DateTimeField(required=False, allow_null=True)

    def validate_bank_product_id(self, value: Any) -> BankProduct | None:
        return None if value is None else _bank_product(value)

    def validate_document_type_id(self, value: Any) -> DocumentType:
        document_type = DocumentType.objects.filter(pk=value).first()
        if document_type is None:
            raise serializers.ValidationError("El tipo documental no existe.")
        return document_type


class DocumentRequirementUpdateSerializer(_RequirementFields):
    """El alcance (producto, tipo, finalidad, perfil, rol y condición) no se edita: si
    cambia, es un requisito nuevo y el anterior se desactiva."""

    is_required = serializers.BooleanField(required=False)
    is_waivable = serializers.BooleanField(required=False)
    minimum_files = serializers.IntegerField(
        min_value=1, max_value=MAX_MINIMUM_FILES, required=False
    )
    alternative_group_code = _group_code_field(required=False)
    validity_days = _validity_days_field(required=False, allow_null=True)
    sort_order = serializers.IntegerField(min_value=0, max_value=MAX_SORT_ORDER, required=False)
    valid_from = serializers.DateTimeField(required=False)
    valid_to = serializers.DateTimeField(required=False, allow_null=True)


# --- Simulación de la lista documental --------------------------------------------------


class PreviewParticipantSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=ParticipantRole.choices)
    employment_profile_code = CatalogItemCodeField(
        catalog_code="employment_profile", required=False, allow_null=True, default=None
    )


class ChecklistPreviewRequestSerializer(StrictSerializer):
    bank_product_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Vacío: solo los requisitos generales.",
    )
    purpose_code = CatalogItemCodeField(
        catalog_code="loan_purpose", required=False, allow_null=True, default=None
    )
    property_condition_code = CatalogItemCodeField(
        catalog_code="property_condition", required=False, allow_null=True, default=None
    )
    participants = serializers.ListField(
        child=PreviewParticipantSerializer(), min_length=1, max_length=MAX_PREVIEW_PARTICIPANTS
    )
    at = serializers.DateTimeField(
        required=False, allow_null=True, default=None, help_text="Por defecto, ahora."
    )

    def validate_bank_product_id(self, value: Any) -> BankProduct | None:
        return None if value is None else _bank_product(value)


class PreviewDocumentSerializer(serializers.Serializer):
    requirement_id = serializers.UUIDField(source="id")
    version = serializers.IntegerField()
    document_type = DocumentTypeRefSerializer()
    is_required = serializers.BooleanField()
    is_waivable = serializers.BooleanField()
    minimum_files = serializers.IntegerField()
    alternative_group_code = serializers.CharField(allow_null=True)
    validity_days = serializers.IntegerField(
        source="effective_validity_days",
        allow_null=True,
        help_text="La del requisito o, si no tiene, la sugerida por el tipo.",
    )
    sort_order = serializers.IntegerField()
    is_general = serializers.SerializerMethodField()

    def get_is_general(self, obj: DocumentRequirement) -> bool:
        """Requisito sin producto: aplica a cualquier banco."""
        return obj.bank_product_id is None


class PreviewParticipantResultSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    role = serializers.CharField()
    employment_profile = CatalogItemRefSerializer(allow_null=True)
    documents = PreviewDocumentSerializer(source="requirements", many=True)


class ChecklistPreviewResponseSerializer(serializers.Serializer):
    participants = PreviewParticipantResultSerializer(many=True)
    application_requirements = PreviewDocumentSerializer(
        many=True, help_text="Documentos de la solicitud: se piden una sola vez, sin participante."
    )
