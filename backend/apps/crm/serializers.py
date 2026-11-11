from datetime import date
from typing import Any, cast

from rest_framework import serializers

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.catalogs.workflow import OpportunityStatus
from apps.crm.models import Client, ClientAddress, Opportunity, OpportunityAssignment
from apps.crm.validators import mask_document_number, normalize_document_number
from apps.identity.models import User
from config.serializers import StrictSerializer
from config.validators import validate_e164_phone


class UserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="get_full_name")


# --- Clientes ---------------------------------------------------------------------------


class ClientSerializer(serializers.ModelSerializer):
    document_type = CatalogItemRefSerializer(source="document_type_item", read_only=True)
    full_name = serializers.CharField(read_only=True)
    origin = CatalogItemRefSerializer(source="origin_item", read_only=True, allow_null=True)
    created_by = UserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "document_type",
            "document_number",
            "first_names",
            "last_names",
            "full_name",
            "birth_date",
            "email",
            "phone",
            "origin",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BrokerClientSerializer(serializers.ModelSerializer):
    """Vista del broker: contacto y resumen. El documento va enmascarado (RF-14)."""

    document_type = serializers.CharField(source="document_type_item.code", read_only=True)
    document_number = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "document_type",
            "document_number",
            "first_names",
            "last_names",
            "full_name",
            "email",
            "phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_document_number(self, obj: Client) -> str:
        return mask_document_number(obj.document_number)


class AddressSerializer(serializers.ModelSerializer):
    address_type = CatalogItemRefSerializer(source="address_type_item", read_only=True)
    city = CatalogItemRefSerializer(source="city_item", read_only=True)
    client_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ClientAddress
        fields = [
            "id",
            "client_id",
            "address_type",
            "city",
            "line1",
            "line2",
            "postal_code",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ClientDetailSerializer(ClientSerializer):
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta(ClientSerializer.Meta):
        fields = [*ClientSerializer.Meta.fields, "addresses"]
        read_only_fields = fields


def _validate_birth_date(value: date | None) -> date | None:
    if value and value >= date.today():
        raise serializers.ValidationError("La fecha de nacimiento debe ser anterior a hoy.")
    return value


class _ClientContactFields(StrictSerializer):
    first_names = serializers.CharField(max_length=120, required=False)
    last_names = serializers.CharField(max_length=120, required=False)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True)
    origin_type = CatalogItemCodeField(catalog_code="lead_origin", required=False, allow_null=True)

    def validate_phone(self, value: str) -> str:
        return validate_e164_phone(value)

    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "origin_type" in data:
            data["origin_item"] = data.pop("origin_type")
        if "document_type_code" in data:
            data["document_type_item"] = data.pop("document_type_code")
        return data


class ClientCreateSerializer(_ClientContactFields):
    document_type_code = CatalogItemCodeField(catalog_code="identity_document_type")
    document_number = serializers.CharField(max_length=40)
    first_names = serializers.CharField(max_length=120)
    last_names = serializers.CharField(max_length=120)
    birth_date = serializers.DateField(required=False, allow_null=True)

    def validate_birth_date(self, value: date | None) -> date | None:
        return _validate_birth_date(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["document_number"] = _normalized_number(attrs)
        return attrs


def _normalized_number(attrs: dict[str, Any]) -> str:
    try:
        return normalize_document_number(attrs["document_type_code"].code, attrs["document_number"])
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({"document_number": exc.detail}) from exc


class ClientUpdateSerializer(_ClientContactFields):
    """Asesor y administrador pueden corregir el documento."""

    document_type_code = CatalogItemCodeField(catalog_code="identity_document_type", required=False)
    document_number = serializers.CharField(max_length=40, required=False)
    birth_date = serializers.DateField(required=False, allow_null=True)

    def __init__(self, *args: Any, client: Client | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client = client

    def validate_birth_date(self, value: date | None) -> date | None:
        return _validate_birth_date(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "document_type_code" in attrs or "document_number" in attrs:
            assert self.client is not None
            attrs.setdefault("document_type_code", self.client.document_type_item)
            attrs.setdefault("document_number", self.client.document_number)
            attrs["document_number"] = _normalized_number(attrs)
        return attrs


class BrokerClientUpdateSerializer(_ClientContactFields):
    """El broker solo actualiza datos de contacto; el documento lo corrige el asesor."""


class AddressCreateSerializer(StrictSerializer):
    address_type_code = CatalogItemCodeField(catalog_code="address_type")
    city_code = CatalogItemCodeField(catalog_code="municipality")
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    is_primary = serializers.BooleanField(required=False, default=False)

    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "address_type_code" in data:
            data["address_type_item"] = data.pop("address_type_code")
        if "city_code" in data:
            data["city_item"] = data.pop("city_code")
        return data


class AddressUpdateSerializer(AddressCreateSerializer):
    address_type_code = CatalogItemCodeField(catalog_code="address_type", required=False)
    city_code = CatalogItemCodeField(catalog_code="municipality", required=False)
    line1 = serializers.CharField(max_length=255, required=False)
    line2 = serializers.CharField(max_length=120, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=12, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)


# --- Oportunidades ----------------------------------------------------------------------


class ClientRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class ProjectRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    partner_name = serializers.CharField(source="partner.__str__")


class OpportunitySerializer(serializers.ModelSerializer):
    client = ClientRefSerializer(read_only=True)
    project = ProjectRefSerializer(read_only=True, allow_null=True)
    origin = CatalogItemRefSerializer(source="origin_item", read_only=True)
    origin_user = UserRefSerializer(read_only=True, allow_null=True)
    assigned_advisor = UserRefSerializer(read_only=True, allow_null=True)
    lost_reason = CatalogItemRefSerializer(
        source="lost_reason_item", read_only=True, allow_null=True
    )

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "client",
            "project",
            "status",
            "origin",
            "origin_user",
            "assigned_advisor",
            "lost_reason",
            "converted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AssignmentSerializer(serializers.ModelSerializer):
    advisor = UserRefSerializer(read_only=True)
    assigned_by = UserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = OpportunityAssignment
        fields = ["id", "advisor", "assigned_by", "reason", "created_at", "ended_at"]
        read_only_fields = fields


class OpportunityDetailSerializer(OpportunitySerializer):
    available_actions = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()

    class Meta(OpportunitySerializer.Meta):
        fields = [*OpportunitySerializer.Meta.fields, "available_actions", "assignments"]
        read_only_fields = fields

    def get_available_actions(self, obj: Opportunity) -> list[str]:
        return self.context["available_actions"]

    def get_assignments(self, obj: Opportunity) -> list[dict[str, Any]]:
        assignments = obj.assignments.select_related("advisor", "assigned_by")
        return cast(list[dict[str, Any]], AssignmentSerializer(assignments, many=True).data)


class BrokerOpportunitySerializer(serializers.ModelSerializer):
    """Resumen para el broker: estado de su prospecto y quién lo atiende."""

    client_name = serializers.CharField(source="client.full_name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, allow_null=True)
    advisor_name = serializers.CharField(
        source="assigned_advisor.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "client_id",
            "client_name",
            "project_id",
            "project_name",
            "status",
            "advisor_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OpportunityCreateSerializer(StrictSerializer):
    client_id = serializers.UUIDField()
    origin_type = CatalogItemCodeField(catalog_code="lead_origin")
    project_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class OpportunityUpdateSerializer(StrictSerializer):
    origin_type = CatalogItemCodeField(catalog_code="lead_origin", required=False)
    project_id = serializers.UUIDField(required=False, allow_null=True)


class AssignmentCreateSerializer(StrictSerializer):
    advisor_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_advisor_id(self, value: Any) -> User:
        user = User.objects.filter(pk=value, deleted_at__isnull=True).first()
        if user is None:
            raise serializers.ValidationError("El usuario no existe.")
        return user


class OpportunityTransitionSerializer(StrictSerializer):
    target_status = serializers.ChoiceField(choices=OpportunityStatus.choices)
    reason_code = CatalogItemCodeField(
        catalog_code="opportunity_lost_reason", required=False, allow_null=True, default=None
    )
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
