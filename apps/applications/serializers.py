import uuid
from collections.abc import Mapping
from datetime import date
from typing import Any, cast

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.bank_evaluation import (
    EvaluationSummary,
    blocking_rows,
    is_current,
    issue,
    warning_rows,
)
from apps.applications.models import (
    ApplicationAssignment,
    ApplicationParticipant,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    ParticipantRole,
    Property,
)
from apps.banking.models import BankProduct
from apps.banking.rule_engine import Outcome
from apps.banking.serializers import BankRefSerializer
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer

# Mismas formas que en CRM: se reutilizan para que OpenAPI no tenga dos componentes
# con el mismo nombre.
from apps.crm.serializers import (
    AssignmentCreateSerializer,
    ClientCreateSerializer,
    ClientSerializer,
    UserRefSerializer,
)
from apps.crm.validators import mask_document_number
from apps.identity.models import User
from config.serializers import StrictSerializer

__all__ = [
    "DETAIL_INCLUDES",
    "ApplicationAssignmentSerializer",
    "ApplicationCreateSerializer",
    "ApplicationDetailSerializer",
    "ApplicationParticipantSerializer",
    "ApplicationPropertyInputSerializer",
    "ApplicationSerializer",
    "ApplicationSummarySerializer",
    "ApplicationUpdateSerializer",
    "AssignmentCreateSerializer",
    "BankRuleEvaluationSerializer",
    "EligibleBankProductSerializer",
    "FinancialProfileInputSerializer",
    "FinancialProfileSerializer",
    "FinancingInputSerializer",
    "FinancingSerializer",
    "IncomeSourceCreateSerializer",
    "IncomeSourceSerializer",
    "IncomeSourceUpdateSerializer",
    "ParticipantCreateSerializer",
    "ParticipantUpdateSerializer",
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
    values.pop("project_id", None)
    return {
        "property_type_item": values.pop("property_type_code"),
        "condition_item": values.pop("condition_code"),
        "city_item": values.pop("city_code"),
        **values,
    }


class ApplicationPropertyInputSerializer(PropertyInputSerializer):
    """``PUT /property`` (API §18.1): reemplazo completo, con el proyecto en el cuerpo."""

    project_id = serializers.UUIDField(required=False, allow_null=True, default=None)


# --- Financiación -----------------------------------------------------------------------


class FinancingSerializer(serializers.ModelSerializer):
    """Preferencia de financiación. El producto elegido vive en la solicitud."""

    application_id = serializers.UUIDField(read_only=True)
    financing_mode = CatalogItemRefSerializer(source="financing_mode_item", read_only=True)
    bank_product = BankProductRefSerializer(
        source="application.bank_product", read_only=True, allow_null=True
    )
    currency_mode = CatalogItemRefSerializer(
        source="currency_mode_item", read_only=True, allow_null=True
    )
    amortization_mode = CatalogItemRefSerializer(
        source="amortization_mode_item", read_only=True, allow_null=True
    )

    class Meta:
        model = FinancingPreference
        fields = [
            "id",
            "application_id",
            "financing_mode",
            "bank_product",
            "requested_amount_cop",
            "term_months",
            "currency_mode",
            "amortization_mode",
            "own_resources_cop",
            "uses_severance_funds",
            "severance_funds_cop",
            "external_approved_amount_cop",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FinancingInputSerializer(StrictSerializer):
    """``PUT /financing`` (API §18.2): reemplazo completo.

    Las reglas que cruzan la modalidad con el producto y los montos las aplica
    ``services.financing_errors``.
    """

    financing_mode_code = CatalogItemCodeField(catalog_code="financing_mode")
    bank_product_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    requested_amount_cop = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    term_months = serializers.IntegerField(
        min_value=1, max_value=32767, required=False, allow_null=True, default=None
    )
    currency_mode_code = CatalogItemCodeField(
        catalog_code="currency_mode", required=False, allow_null=True, default=None
    )
    amortization_mode_code = CatalogItemCodeField(
        catalog_code="amortization_mode", required=False, allow_null=True, default=None
    )
    own_resources_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    uses_severance_funds = serializers.BooleanField(required=False, default=False)
    severance_funds_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    external_approved_amount_cop = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )

    def model_values(self) -> dict[str, Any]:
        """Campos del modelo, sin ``bank_product_id`` (va en la solicitud)."""
        values = dict(self.validated_data)
        values.pop("bank_product_id")
        return {
            "financing_mode_item": values.pop("financing_mode_code"),
            "currency_mode_item": values.pop("currency_mode_code"),
            "amortization_mode_item": values.pop("amortization_mode_code"),
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


# --- Participantes, perfil financiero e ingresos (API §17) ------------------------------

ADDITIONAL_ROLE_CHOICES = [
    (role.value, role.label)
    for role in (ParticipantRole.CO_APPLICANT, ParticipantRole.SOLIDARY_DEBTOR)
]
# Datos de identidad con los que `POST /participants` crea el cliente (mismas reglas
# que `POST /clients`).
CLIENT_IDENTITY_FIELDS = (
    "document_type_code",
    "document_number",
    "first_names",
    "last_names",
    "birth_date",
    "email",
    "phone",
)


class ApplicationParticipantSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(read_only=True)
    client = ClientSerializer(read_only=True)
    financial_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationParticipant
        fields = [
            "id",
            "application_id",
            "client",
            "role",
            "contributes_income",
            "income_share_cop",
            "is_active",
            "financial_profile_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_financial_profile_id(self, obj: ApplicationParticipant) -> uuid.UUID | None:
        profile = getattr(obj, "financial_profile", None)
        return None if profile is None else profile.pk


class ParticipantCreateSerializer(StrictSerializer):
    """Un cliente visible (``client_id``) o sus datos de identidad, nunca ambos."""

    role_code = serializers.ChoiceField(choices=ADDITIONAL_ROLE_CHOICES)
    client_id = serializers.UUIDField(required=False)
    contributes_income = serializers.BooleanField(required=False, default=True)
    income_share_cop = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    # Los valida `ClientCreateSerializer`; se declaran aquí para el esquema.
    document_type_code = serializers.CharField(required=False)
    document_number = serializers.CharField(max_length=40, required=False)
    first_names = serializers.CharField(max_length=120, required=False)
    last_names = serializers.CharField(max_length=120, required=False)
    birth_date = serializers.DateField(required=False, allow_null=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        identity = {
            field: self.initial_data[field]
            for field in CLIENT_IDENTITY_FIELDS
            if field in self.initial_data
        }
        if "client_id" in attrs:
            if identity:
                raise serializers.ValidationError(
                    {
                        field: ["Envía `client_id` o los datos del cliente, no ambos."]
                        for field in identity
                    }
                )
            attrs["client_data"] = None
            return attrs
        client = ClientCreateSerializer(data=identity)
        if not client.is_valid():
            raise serializers.ValidationError(client.errors)
        attrs["client_data"] = client.to_service_data()
        return attrs


class ParticipantUpdateSerializer(StrictSerializer):
    role_code = serializers.ChoiceField(choices=ADDITIONAL_ROLE_CHOICES, required=False)
    contributes_income = serializers.BooleanField(required=False)
    income_share_cop = serializers.IntegerField(min_value=0, required=False, allow_null=True)

    def changes(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "role_code" in data:
            data["role"] = data.pop("role_code")
        return data


class FinancialProfileSerializer(serializers.ModelSerializer):
    participant_id = serializers.UUIDField(read_only=True)
    employment_profile = CatalogItemRefSerializer(source="employment_profile_item", read_only=True)
    contract_type = CatalogItemRefSerializer(
        source="contract_type_item", read_only=True, allow_null=True
    )
    funds_origin = CatalogItemRefSerializer(
        source="funds_origin_item", read_only=True, allow_null=True
    )
    # Informativo: no tiene que coincidir con `monthly_income_cop`.
    income_sources_total_cop = serializers.IntegerField(read_only=True)

    class Meta:
        model = FinancialProfile
        fields = [
            "id",
            "participant_id",
            "employment_profile",
            "contract_type",
            "employer_name",
            "job_title",
            "employment_start_date",
            "monthly_income_cop",
            "income_sources_total_cop",
            "monthly_expenses_cop",
            "assets_cop",
            "liabilities_cop",
            "funds_origin",
            "data_confirmed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FinancialProfileInputSerializer(StrictSerializer):
    """Reemplazo completo (``PUT``): lo que no llega vuelve a su valor por omisión."""

    employment_profile_code = CatalogItemCodeField(catalog_code="employment_profile")
    contract_type_code = CatalogItemCodeField(
        catalog_code="contract_type", required=False, allow_null=True, default=None
    )
    employer_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    employment_start_date = serializers.DateField(required=False, allow_null=True, default=None)
    monthly_income_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    monthly_expenses_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    assets_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    liabilities_cop = serializers.IntegerField(min_value=0, required=False, default=0)
    funds_origin_code = CatalogItemCodeField(
        catalog_code="funds_origin", required=False, allow_null=True, default=None
    )

    def validate_employment_start_date(self, value: date | None) -> date | None:
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("La fecha de ingreso no puede ser futura.")
        return value

    def model_values(self) -> dict[str, Any]:
        values = dict(self.validated_data)
        return {
            "employment_profile_item": values.pop("employment_profile_code"),
            "contract_type_item": values.pop("contract_type_code"),
            "funds_origin_item": values.pop("funds_origin_code"),
            **values,
        }


class IncomeSourceSerializer(serializers.ModelSerializer):
    financial_profile_id = serializers.UUIDField(read_only=True)
    source_type = CatalogItemRefSerializer(source="source_type_item", read_only=True)

    class Meta:
        model = IncomeSource
        fields = [
            "id",
            "financial_profile_id",
            "source_type",
            "payer_name",
            "monthly_amount_cop",
            "start_date",
            "is_primary",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class IncomeSourceCreateSerializer(StrictSerializer):
    source_type_code = CatalogItemCodeField(catalog_code="income_source_type")
    payer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    monthly_amount_cop = serializers.IntegerField(min_value=0)
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    is_primary = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

    def model_values(self) -> dict[str, Any]:
        values = dict(self.validated_data)
        if "source_type_code" in values:
            values["source_type_item"] = values.pop("source_type_code")
        return values


class IncomeSourceUpdateSerializer(IncomeSourceCreateSerializer):
    source_type_code = CatalogItemCodeField(catalog_code="income_source_type", required=False)
    payer_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    monthly_amount_cop = serializers.IntegerField(min_value=0, required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)


# --- Detalle de la solicitud ------------------------------------------------------------

# Bloques que admite `?include=` en el detalle. `property` y `assignments` salen siempre.
DETAIL_INCLUDES = ("participants", "property", "financing")


class ApplicationDetailSerializer(ApplicationSerializer):
    """Expediente interno. ``context["include"]`` agrega `participants` y `financing`.

    Los bloques opcionales no se declaran de solo lectura para que OpenAPI no los marque
    como obligatorios: faltan en la respuesta si no se pidieron. `participants` lee los
    vigentes precargados en ``active_participants`` (``services.application_detail``).
    """

    property = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()
    participants = ApplicationParticipantSerializer(
        source="active_participants",
        many=True,
        required=False,
        help_text="Participantes vigentes. Solo con `include=participants`.",
    )
    financing = FinancingSerializer(
        required=False,
        allow_null=True,
        help_text="Preferencia de financiación. Solo con `include=financing`.",
    )

    class Meta(ApplicationSerializer.Meta):
        fields = [
            *ApplicationSerializer.Meta.fields,
            "property",
            "assignments",
            "participants",
            "financing",
        ]
        read_only_fields = [*ApplicationSerializer.Meta.fields, "property", "assignments"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        include = self.context.get("include", ())
        for name in ("participants", "financing"):
            if name not in include:
                self.fields.pop(name)

    def get_property(self, obj: CreditApplication) -> dict[str, Any] | None:
        prop = getattr(obj, "financed_property", None)
        return None if prop is None else cast(dict[str, Any], PropertySerializer(prop).data)

    def get_assignments(self, obj: CreditApplication) -> list[dict[str, Any]]:
        assignments = obj.assignments.select_related("advisor", "assigned_by")
        return cast(
            list[dict[str, Any]], ApplicationAssignmentSerializer(assignments, many=True).data
        )


# --- Reglas bancarias (API §18.2) -------------------------------------------------------


class RuleIssueSerializer(serializers.Serializer):
    """Regla incumplida (`FAILED`) o sin datos para decidir (`MISSING_DATA`)."""

    rule_code = serializers.CharField()
    outcome = serializers.ChoiceField(choices=[Outcome.FAILED.value, Outcome.MISSING_DATA.value])
    message = serializers.CharField()
    field = serializers.CharField(
        allow_null=True,
        help_text=(
            "Campo de la lista segura (`financing.requested_amount_cop`): el primero que "
            "falta o, si se incumple, el primero que cita la condición."
        ),
    )
    unresolved_fields = serializers.ListField(child=serializers.CharField())


class BankRuleEvaluationSerializer(serializers.ModelSerializer):
    """Evaluación guardada. ``context["application"]`` decide ``is_current``."""

    bank_product_id = serializers.UUIDField(read_only=True)
    is_current = serializers.SerializerMethodField(
        help_text="Corresponde a la versión y al producto actuales de la solicitud."
    )
    eligible = serializers.BooleanField(source="is_eligible", read_only=True)
    blocking = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    evaluated_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = BankRuleEvaluation
        fields = [
            "id",
            "bank_product_id",
            "application_version",
            "is_current",
            "eligible",
            "blocking",
            "warnings",
            "evaluated_at",
        ]
        read_only_fields = fields

    def get_is_current(self, obj: BankRuleEvaluation) -> bool:
        application: CreditApplication = self.context["application"]
        return is_current(obj, application)

    @extend_schema_field(RuleIssueSerializer(many=True))
    def get_blocking(self, obj: BankRuleEvaluation) -> list[dict[str, Any]]:
        return [issue(row) for row in blocking_rows(obj.result_snapshot["rules"])]

    @extend_schema_field(RuleIssueSerializer(many=True))
    def get_warnings(self, obj: BankRuleEvaluation) -> list[dict[str, Any]]:
        return [issue(row) for row in warning_rows(obj.result_snapshot["rules"])]


class ProductEligibilitySerializer(serializers.Serializer):
    eligible = serializers.BooleanField()
    blocking_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()


class EligibleBankProductSerializer(serializers.ModelSerializer):
    """Producto disponible para la finalidad, con una evaluación no guardada.

    ``context["evaluations"]`` trae el resumen de cada producto, por id.
    """

    bank = BankRefSerializer(read_only=True)
    product_type_code = serializers.CharField(source="product_type_item.code", read_only=True)
    evaluation = serializers.SerializerMethodField()

    class Meta:
        model = BankProduct
        fields = [
            "id",
            "code",
            "name",
            "bank",
            "product_type_code",
            "min_amount_cop",
            "max_amount_cop",
            "min_term_months",
            "max_term_months",
            "evaluation",
        ]
        read_only_fields = fields

    @extend_schema_field(ProductEligibilitySerializer)
    def get_evaluation(self, obj: BankProduct) -> dict[str, Any]:
        summary: EvaluationSummary = self.context["evaluations"][obj.pk]
        return {
            "eligible": summary.eligible,
            "blocking_count": summary.blocking_count,
            "warning_count": summary.warning_count,
        }
