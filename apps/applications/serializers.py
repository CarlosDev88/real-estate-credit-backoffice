from collections.abc import Mapping
from typing import Any, cast

from django.utils import timezone
from rest_framework import serializers

from apps.applications.models import ApplicationAssignment, CreditApplication, Property
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer

# Mismas formas que en CRM: se reutilizan para que OpenAPI no tenga dos componentes
# con el mismo nombre.
from apps.crm.serializers import AssignmentCreateSerializer, UserRefSerializer
from apps.crm.validators import mask_document_number
from apps.identity.models import User
from config.serializers import StrictSerializer

__all__ = [
    "ApplicationAssignmentSerializer",
    "ApplicationCreateSerializer",
    "ApplicationDetailSerializer",
    "ApplicationSerializer",
    "ApplicationSummarySerializer",
    "ApplicationUpdateSerializer",
    "AssignmentCreateSerializer",
    "PropertyInputSerializer",
    "PropertySerializer",
    "property_model_values",
]


class NamedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class BankProductRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    bank = NamedRefSerializer()


class ApplicantRefSerializer(serializers.Serializer):
    """Titular de la solicitud: el cliente de la oportunidad."""

    id = serializers.UUIDField()
    full_name = serializers.CharField()
    document_type = serializers.CharField(source="document_type_item.code")
    document_number = serializers.CharField()


# --- Inmueble ---------------------------------------------------------------------------


class PropertySerializer(serializers.ModelSerializer):
    project = NamedRefSerializer(read_only=True, allow_null=True)
    property_type = CatalogItemRefSerializer(source="property_type_item", read_only=True)
    condition = CatalogItemRefSerializer(source="condition_item", read_only=True)
    city = CatalogItemRefSerializer(source="city_item", read_only=True)

    class Meta:
        model = Property
        fields = [
            "id",
            "project",
            "property_type",
            "condition",
            "city",
            "address",
            "unit_reference",
            "estimated_value_cop",
            "is_owned_by_applicant",
            "ownership_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PropertyInputSerializer(StrictSerializer):
    """Datos del inmueble. El proyecto se valida aparte (debe estar `ACTIVE`)."""

    property_type_code = CatalogItemCodeField(catalog_code="property_type")
    condition_code = CatalogItemCodeField(catalog_code="property_condition")
    city_code = CatalogItemCodeField(catalog_code="municipality")
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    unit_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    estimated_value_cop = serializers.IntegerField(min_value=0)
    is_owned_by_applicant = serializers.BooleanField(required=False, allow_null=True, default=None)
    ownership_notes = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


def property_model_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """Pasa los datos validados de ``PropertyInputSerializer`` a campos del modelo."""
    values = dict(data)
    return {
        "property_type_item": values.pop("property_type_code"),
        "condition_item": values.pop("condition_code"),
        "city_item": values.pop("city_code"),
        **values,
    }


# --- Solicitud --------------------------------------------------------------------------


class ApplicationAssignmentSerializer(serializers.ModelSerializer):
    advisor = UserRefSerializer(read_only=True)
    assigned_by = UserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = ApplicationAssignment
        fields = ["id", "advisor", "assigned_by", "reason", "created_at", "ended_at"]
        read_only_fields = fields


class ApplicationSerializer(serializers.ModelSerializer):
    """Vista interna (administrador y asesor) para listas."""

    opportunity_id = serializers.UUIDField(read_only=True)
    applicant = ApplicantRefSerializer(source="opportunity.client", read_only=True)
    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True)
    bank_product = BankProductRefSerializer(read_only=True, allow_null=True)
    assigned_advisor = UserRefSerializer(read_only=True)
    origin = CatalogItemRefSerializer(source="opportunity.origin_item", read_only=True)
    project = serializers.SerializerMethodField()
    withdrawal_reason = CatalogItemRefSerializer(
        source="withdrawal_reason_item", read_only=True, allow_null=True
    )

    class Meta:
        model = CreditApplication
        fields = [
            "id",
            "code",
            "status",
            "opportunity_id",
            "applicant",
            "purpose",
            "bank_product",
            "assigned_advisor",
            "origin",
            "project",
            "version",
            "current_stage_started_at",
            "ready_to_file_at",
            "withdrawn_at",
            "withdrawal_reason",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_project(self, obj: CreditApplication) -> dict[str, Any] | None:
        prop = getattr(obj, "financed_property", None)
        if prop is None or prop.project is None:
            return None
        return {"id": str(prop.project.pk), "name": prop.project.name}


class ApplicationDetailSerializer(ApplicationSerializer):
    property = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()

    class Meta(ApplicationSerializer.Meta):
        fields = [*ApplicationSerializer.Meta.fields, "property", "assignments"]
        read_only_fields = fields

    def get_property(self, obj: CreditApplication) -> dict[str, Any] | None:
        prop = getattr(obj, "financed_property", None)
        return None if prop is None else cast(dict[str, Any], PropertySerializer(prop).data)

    def get_assignments(self, obj: CreditApplication) -> list[dict[str, Any]]:
        assignments = obj.assignments.select_related("advisor", "assigned_by")
        return cast(
            list[dict[str, Any]], ApplicationAssignmentSerializer(assignments, many=True).data
        )


class ApplicationSummarySerializer(serializers.ModelSerializer):
    """Resumen operativo (API §16.1 `/summary`): lo único que recibe el broker.

    Sin datos financieros, inmueble ni documento completo del titular.
    """

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True)
    client_name = serializers.CharField(source="opportunity.client.full_name", read_only=True)
    client_document_number = serializers.SerializerMethodField()
    bank_name = serializers.CharField(
        source="bank_product.bank.name", read_only=True, allow_null=True
    )
    product_name = serializers.CharField(
        source="bank_product.name", read_only=True, allow_null=True
    )
    advisor_name = serializers.CharField(source="assigned_advisor.get_full_name", read_only=True)
    days_in_stage = serializers.SerializerMethodField()

    class Meta:
        model = CreditApplication
        fields = [
            "id",
            "code",
            "status",
            "status_label",
            "opportunity_id",
            "purpose",
            "client_name",
            "client_document_number",
            "bank_name",
            "product_name",
            "advisor_name",
            "current_stage_started_at",
            "days_in_stage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_client_document_number(self, obj: CreditApplication) -> str:
        return mask_document_number(obj.opportunity.client.document_number)

    def get_days_in_stage(self, obj: CreditApplication) -> int:
        return (timezone.now() - obj.current_stage_started_at).days


# --- Entradas ---------------------------------------------------------------------------


class ApplicationCreateSerializer(StrictSerializer):
    opportunity_id = serializers.UUIDField()
    purpose_code = CatalogItemCodeField(catalog_code="loan_purpose")
    assigned_advisor_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    project_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    property = PropertyInputSerializer(required=False, allow_null=True, default=None)

    def validate_assigned_advisor_id(self, value: Any) -> User | None:
        if value is None:
            return None
        user = User.objects.filter(pk=value, deleted_at__isnull=True).first()
        if user is None:
            raise serializers.ValidationError("El usuario no existe.")
        return user

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["project_id"] is not None and attrs["property"] is None:
            raise serializers.ValidationError(
                {"project_id": ["El proyecto pertenece al inmueble: envía también `property`."]}
            )
        return attrs

    def property_values(self) -> dict[str, Any] | None:
        data = self.validated_data["property"]
        return None if data is None else property_model_values(data)


class ApplicationUpdateSerializer(StrictSerializer):
    """Campos editables antes de `FILED` (API §16.2). El asesor va por `/assignments`."""

    purpose_code = CatalogItemCodeField(catalog_code="loan_purpose", required=False)
    bank_product_id = serializers.UUIDField(required=False, allow_null=True)
