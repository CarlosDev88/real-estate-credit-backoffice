import json
from typing import Any

from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition
from apps.catalogs.workflow import FlowType
from config.serializers import StrictSerializer

METADATA_MAX_BYTES = 4096
METADATA_MAX_KEYS = 30

catalog_code_validator = RegexValidator(
    r"^[a-z][a-z0-9_]{1,49}$",
    "Usa minúsculas, números y guion bajo, empezando por una letra (ej. loan_purpose).",
)
item_code_validator = RegexValidator(
    r"^[A-Z0-9][A-Z0-9_]{0,49}$",
    "Usa mayúsculas, números y guion bajo (ej. PURCHASE_NEW o 11001).",
)
transition_code_validator = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,79}$",
    "Usa mayúsculas, números y guion bajo, empezando por una letra (ej. MARK_READY).",
)


def validate_metadata(value: Any) -> None:
    if not isinstance(value, dict):
        raise serializers.ValidationError("Debe ser un objeto JSON.")
    if len(value) > METADATA_MAX_KEYS:
        raise serializers.ValidationError(f"Máximo {METADATA_MAX_KEYS} claves.")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > METADATA_MAX_BYTES:
        raise serializers.ValidationError(f"Máximo {METADATA_MAX_BYTES} bytes.")


# --- Catálogos ------------------------------------------------------------------------


class CatalogSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Catalog
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_manageable",
            "is_public",
            "version",
            "items_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CatalogCreateSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50, validators=[catalog_code_validator])
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    is_public = serializers.BooleanField(required=False, default=False)


class CatalogUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False)


# --- Valores --------------------------------------------------------------------------


class CatalogItemSerializer(serializers.ModelSerializer):
    catalog_id = serializers.UUIDField(read_only=True)
    catalog_code = serializers.CharField(source="catalog.code", read_only=True)
    parent_id = serializers.UUIDField(source="parent_item_id", read_only=True, allow_null=True)

    class Meta:
        model = CatalogItem
        fields = [
            "id",
            "catalog_id",
            "catalog_code",
            "code",
            "label",
            "description",
            "parent_id",
            "sort_order",
            "is_active",
            "valid_from",
            "valid_to",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CatalogItemCreateSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50, validators=[item_code_validator])
    label = serializers.CharField(max_length=180)  # type: ignore[assignment]
    description = serializers.CharField(required=False, allow_blank=True, default="")
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    sort_order = serializers.IntegerField(required=False, allow_null=True, default=None)
    valid_from = serializers.DateField(required=False, allow_null=True, default=None)
    valid_to = serializers.DateField(required=False, allow_null=True, default=None)
    metadata = serializers.JSONField(required=False, default=dict, validators=[validate_metadata])

    def validate_parent_id(self, value: Any) -> CatalogItem | None:
        if value is None:
            return None
        parent = CatalogItem.objects.filter(pk=value).first()
        if parent is None:
            raise serializers.ValidationError("El valor padre no existe.")
        return parent

    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        data["parent_item"] = data.pop("parent_id")
        return data


class CatalogItemUpdateSerializer(StrictSerializer):
    """Solo etiqueta, descripción, metadatos y vigencia. El código no se renombra."""

    label = serializers.CharField(max_length=180, required=False)  # type: ignore[assignment]
    description = serializers.CharField(required=False, allow_blank=True)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_to = serializers.DateField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, validators=[validate_metadata])


class CatalogItemOrderSerializer(StrictSerializer):
    item_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)

    def validate_item_ids(self, value: list[Any]) -> list[Any]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Hay valores repetidos.")
        return value


# --- Metadatos ------------------------------------------------------------------------


class MetadataItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    description = serializers.CharField()
    order = serializers.IntegerField()
    active = serializers.BooleanField()
    parent_id = serializers.UUIDField(allow_null=True)
    parent_code = serializers.CharField(allow_null=True)
    metadata = serializers.DictField()


class MetadataCatalogSerializer(serializers.Serializer):
    catalog = serializers.CharField()
    name = serializers.CharField()
    version = serializers.IntegerField()
    items = MetadataItemSerializer(many=True)


class BootstrapSerializer(serializers.Serializer):
    metadata_version = serializers.IntegerField()
    actor = serializers.CharField(allow_null=True)
    permissions = serializers.ListField(child=serializers.CharField())
    catalogs = serializers.DictField(child=MetadataItemSerializer(many=True))
    on_demand_catalogs = serializers.ListField(child=serializers.CharField())
    features = serializers.DictField(child=serializers.BooleanField())


# --- Transiciones ---------------------------------------------------------------------


class WorkflowTransitionSerializer(serializers.ModelSerializer):
    required_permission = serializers.SerializerMethodField()
    guard_code = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowTransition
        fields = [
            "id",
            "flow_type",
            "code",
            "from_status",
            "to_status",
            "label",
            "required_permission",
            "guard_code",
            "roles",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_required_permission(self, obj: WorkflowTransition) -> str | None:
        return obj.required_permission.code if obj.required_permission else None

    def get_guard_code(self, obj: WorkflowTransition) -> str | None:
        return obj.guard_code or None

    def get_roles(self, obj: WorkflowTransition) -> list[str]:
        return sorted(role.code for role in obj.roles.all())


class WorkflowTransitionCreateSerializer(StrictSerializer):
    flow_type = serializers.ChoiceField(choices=FlowType.choices)
    code = serializers.CharField(max_length=80, validators=[transition_code_validator])
    from_status = serializers.CharField(max_length=40)
    to_status = serializers.CharField(max_length=40)
    label = serializers.CharField(max_length=120)  # type: ignore[assignment]
    required_permission = serializers.CharField(
        max_length=100, required=False, allow_null=True, default=None
    )
    guard_code = serializers.CharField(
        max_length=80, required=False, allow_null=True, allow_blank=True, default=None
    )
    roles = serializers.ListField(child=serializers.CharField(max_length=50), allow_empty=False)


class WorkflowTransitionUpdateSerializer(StrictSerializer):
    from_status = serializers.CharField(max_length=40, required=False)
    to_status = serializers.CharField(max_length=40, required=False)
    label = serializers.CharField(max_length=120, required=False)  # type: ignore[assignment]
    required_permission = serializers.CharField(max_length=100, required=False, allow_null=True)
    guard_code = serializers.CharField(
        max_length=80, required=False, allow_null=True, allow_blank=True
    )
    roles = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, allow_empty=False
    )
