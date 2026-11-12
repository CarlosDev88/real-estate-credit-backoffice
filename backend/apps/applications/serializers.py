import uuid
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any, cast

from django.conf import settings
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
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    ParticipantRole,
    Property,
)
from apps.applications.quick_filters import WAITING_STATUSES
from apps.applications.stages import INTERNAL_STAGES, StageState, progress_stages
from apps.banking.models import BankProduct
from apps.banking.rule_engine import Outcome
from apps.banking.serializers import BankRefSerializer
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.models import WorkflowTransition
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.catalogs.workflow import ApplicationStatus

# Mismas formas que en CRM: se reutilizan para que OpenAPI no tenga dos componentes
# con el mismo nombre.
from apps.crm.serializers import (
    AssignmentCreateSerializer,
    ClientCreateSerializer,
    ClientSerializer,
    UserRefSerializer,
)
from apps.crm.validators import mask_document_number
from apps.documents.models import SlotStatus
from apps.identity.models import BuyerSession, User
from config.serializers import ErrorDetailSerializer, StrictSerializer

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
    "AvailableActionSerializer",
    "BankRuleEvaluationSerializer",
    "CompletenessSerializer",
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
    "StatusChangeSerializer",
    "StatusHistorySerializer",
    "StatusTransitionSerializer",
    "WithdrawalSerializer",
    "property_model_values",
]


class NamedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class BankProductRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    product_type = CatalogItemRefSerializer(
        source="product_type_item", help_text="Tipo de crédito (catálogo `bank_product_type`)."
    )
    bank = BankRefSerializer()


class ParticipantsSummarySerializer(serializers.Serializer):
    """Participantes activos además del titular, para el texto "+ 1 co-solicitante"."""

    co_applicants = serializers.IntegerField()
    solidary_debtors = serializers.IntegerField()


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

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    opportunity_id = serializers.UUIDField(read_only=True)
    applicant = ApplicantRefSerializer(source="opportunity.client", read_only=True)
    participants_summary = serializers.SerializerMethodField()
    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True)
    bank_product = BankProductRefSerializer(read_only=True, allow_null=True)
    requested_amount_cop = serializers.IntegerField(
        source="financing.requested_amount_cop",
        read_only=True,
        allow_null=True,
        help_text="Monto solicitado de la financiación; `null` si aún no hay financiación.",
    )
    completeness_pct = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="Completitud guardada (0 a 100), la misma regla de `/completeness`. `null` "
        "si todavía no se calculó.",
    )
    ready_to_file_blocked = serializers.SerializerMethodField(
        help_text="Solo en `READY_TO_FILE`: `true` si ya no cumple la guarda (documento "
        "rechazado, reabierto, vencido o versión nueva), `false` si cumple. `null` en los "
        "demás estados o sin valor calculado."
    )
    last_buyer_activity_at = serializers.SerializerMethodField(
        help_text="Última vez que el comprador usó el portal en esta solicitud; `null` si "
        "nunca entró. Sirve para el texto del aviso de inactividad."
    )
    buyer_inactive = serializers.SerializerMethodField(
        help_text="Solo en la pestaña `waiting` (esperando al comprador): `true` si la última "
        "actividad del comprador (o, si nunca entró, el inicio de la etapa) tiene más de "
        "`BUYER_INACTIVITY_DAYS` días (3), `false` si no. `null` en los demás estados."
    )
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
            "status_label",
            "opportunity_id",
            "applicant",
            "participants_summary",
            "purpose",
            "bank_product",
            "requested_amount_cop",
            "completeness_pct",
            "ready_to_file_blocked",
            "last_buyer_activity_at",
            "buyer_inactive",
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

    @staticmethod
    def _last_buyer_activity(obj: CreditApplication) -> datetime | None:
        """Lee la anotación de ``services.applications_queryset``; si la instancia no la
        trae, la consulta."""
        if hasattr(obj, "last_buyer_activity_at"):
            return cast(datetime | None, obj.last_buyer_activity_at)
        return (
            BuyerSession.objects.filter(application=obj, last_seen_at__isnull=False)
            .order_by("-last_seen_at")
            .values_list("last_seen_at", flat=True)
            .first()
        )

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_buyer_activity_at(self, obj: CreditApplication) -> str | None:
        activity = self._last_buyer_activity(obj)
        # Mismo formato y zona horaria que los demás campos de fecha de la API.
        return None if activity is None else serializers.DateTimeField().to_representation(activity)

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_buyer_inactive(self, obj: CreditApplication) -> bool | None:
        """Con la anotación y los campos de la fila, sin consultas (precisión C)."""
        if obj.status not in WAITING_STATUSES:
            return None
        reference = self._last_buyer_activity(obj) or obj.current_stage_started_at
        return timezone.now() - reference > timedelta(days=settings.BUYER_INACTIVITY_DAYS)

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_ready_to_file_blocked(self, obj: CreditApplication) -> bool | None:
        """Con los campos de la fila, sin consultas."""
        if obj.status != ApplicationStatus.READY_TO_FILE or obj.ready_to_file_ok is None:
            return None
        return not obj.ready_to_file_ok

    @extend_schema_field(ParticipantsSummarySerializer)
    def get_participants_summary(self, obj: CreditApplication) -> dict[str, int]:
        """Lee los conteos de ``services.applications_queryset``; si la instancia no los
        trae (no salió de ese queryset), los consulta."""
        co_applicants = getattr(obj, "co_applicants_count", None)
        solidary_debtors = getattr(obj, "solidary_debtors_count", None)
        if co_applicants is None or solidary_debtors is None:
            active = obj.participants.filter(is_active=True)
            co_applicants = active.filter(role=ParticipantRole.CO_APPLICANT).count()
            solidary_debtors = active.filter(role=ParticipantRole.SOLIDARY_DEBTOR).count()
        return {"co_applicants": co_applicants, "solidary_debtors": solidary_debtors}


class QuickFilterSerializer(serializers.Serializer):
    """Pestaña rápida del listado con su conteo dentro del alcance del actor."""

    code = serializers.CharField(help_text="Valor de `quick_filter` en el listado.")
    label = serializers.CharField()  # type: ignore[assignment]
    statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=ApplicationStatus.choices),
        help_text="Estados que agrupa; vacío en `all`.",
    )
    count = serializers.IntegerField()


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
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    financial_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationParticipant
        fields = [
            "id",
            "application_id",
            "client",
            "role",
            "role_label",
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


class AvailableActionSerializer(serializers.ModelSerializer):
    """Transición que el actor puede ejecutar ahora; la guarda se evalúa al ejecutarla."""

    target_status = serializers.ChoiceField(source="to_status", choices=ApplicationStatus.choices)

    class Meta:
        model = WorkflowTransition
        fields = ["code", "label", "target_status", "guard_code"]
        read_only_fields = fields


# Bloques que admite `?include=` en el detalle. `property` y `assignments` salen siempre.
DETAIL_INCLUDES = ("participants", "property", "financing")


class ProgressStageSerializer(serializers.Serializer):
    """Etapa de avance de la solicitud. La comparten el expediente interno
    (``progress_stages``) y el portal del comprador (``stages``)."""

    code = serializers.CharField()
    # `label` choca con el atributo `Field.label` de los stubs de DRF.
    label = serializers.CharField()  # type: ignore[assignment]
    state = serializers.ChoiceField(choices=StageState.choices)
    state_label = serializers.CharField(help_text="Listo, En curso o Pendiente.")


class ApplicationDetailSerializer(ApplicationSerializer):
    """Expediente interno. ``context["include"]`` agrega `participants` y `financing`, y
    ``context["available_actions"]`` trae las transiciones que el actor puede ejecutar.

    Los bloques opcionales no se declaran de solo lectura para que OpenAPI no los marque
    como obligatorios: faltan en la respuesta si no se pidieron. `participants` lee los
    vigentes precargados en ``active_participants`` (``services.application_detail``).
    """

    property = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()
    progress_stages = serializers.SerializerMethodField(
        help_text="Las 8 etapas del expediente con su estado (`done`, `current` o "
        "`pending`). Vacía en `WITHDRAWN`, `CANCELLED`, `OWN_FUNDS` y "
        "`EXTERNAL_CREDIT_APPROVED`."
    )
    available_actions = serializers.SerializerMethodField(
        help_text="Transiciones que el actor puede ejecutar ahora (rol y permiso; la guarda "
        "se evalúa al ejecutarla). `WITHDRAW_*` se ejecuta por `/withdrawals`."
    )
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
            "progress_stages",
            "available_actions",
            "participants",
            "financing",
        ]
        read_only_fields = [
            *ApplicationSerializer.Meta.fields,
            "property",
            "assignments",
            "progress_stages",
            "available_actions",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        include = self.context.get("include", ())
        for name in ("participants", "financing"):
            if name not in include:
                self.fields.pop(name)

    def get_property(self, obj: CreditApplication) -> dict[str, Any] | None:
        prop = getattr(obj, "financed_property", None)
        return None if prop is None else cast(dict[str, Any], PropertySerializer(prop).data)

    @extend_schema_field(ProgressStageSerializer(many=True))
    def get_progress_stages(self, obj: CreditApplication) -> list[dict[str, str]]:
        return progress_stages(INTERNAL_STAGES, obj.status)

    @extend_schema_field(AvailableActionSerializer(many=True))
    def get_available_actions(self, obj: CreditApplication) -> list[dict[str, Any]]:
        actions: list[WorkflowTransition] = self.context["available_actions"]
        return cast(list[dict[str, Any]], AvailableActionSerializer(actions, many=True).data)

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


# --- Estados, desistimiento, acciones e historial (API §16.3) ---------------------------


class _StatusChangeInputSerializer(StrictSerializer):
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    expected_version = serializers.IntegerField(
        min_value=1, help_text="Versión de la solicitud que se consultó (`ETag`)."
    )


class StatusTransitionSerializer(_StatusChangeInputSerializer):
    """``POST /status-transitions``. `WITHDRAWN` va por `/withdrawals`."""

    target_status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    reason_code = CatalogItemCodeField(
        catalog_code="application_transition_reason",
        required=False,
        allow_null=True,
        default=None,
        help_text="Obligatorio al pasar a `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED`.",
    )


class WithdrawalSerializer(_StatusChangeInputSerializer):
    reason_code = CatalogItemCodeField(catalog_code="application_withdrawal_reason")


class StatusChangeSerializer(serializers.Serializer):
    """Respuesta de un cambio de estado (API §16.3)."""

    application_id = serializers.UUIDField(source="application.pk")
    previous_status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    status = serializers.ChoiceField(source="application.status", choices=ApplicationStatus.choices)
    version = serializers.IntegerField(source="application.version")
    transitioned_at = serializers.DateTimeField()


class StatusHistorySerializer(serializers.ModelSerializer):
    transition_code = serializers.CharField(
        source="transition.code", read_only=True, allow_null=True
    )
    reason = CatalogItemRefSerializer(source="reason_item", read_only=True, allow_null=True)
    actor = UserRefSerializer(source="actor_user", read_only=True, allow_null=True)
    # El cambio lo hizo el comprador desde su portal (`actor` queda en `null`).
    buyer_session_id = serializers.UUIDField(
        source="actor_buyer_session_id", read_only=True, allow_null=True
    )

    class Meta:
        model = ApplicationStatusHistory
        fields = [
            "id",
            "from_status",
            "to_status",
            "transition_code",
            "reason",
            "comment",
            "actor",
            "buyer_session_id",
            "application_version",
            "created_at",
        ]
        read_only_fields = fields


# --- Completitud ------------------------------------------------------------------------


class CompletenessItemSerializer(serializers.Serializer):
    code = serializers.ChoiceField(
        choices=["property", "financing", "bank_product", "bank_evaluation", "financial_profile"]
    )
    complete = serializers.BooleanField()
    message = serializers.CharField()
    participant_id = serializers.UUIDField(
        allow_null=True, help_text="Solo en `financial_profile`."
    )


class CompletenessDocumentTypeSerializer(serializers.Serializer):
    code = serializers.CharField(source="document_type_code")
    name = serializers.CharField(source="document_type_name")


class CompletenessDocumentSlotSerializer(serializers.Serializer):
    slot_id = serializers.UUIDField()
    participant_id = serializers.UUIDField(
        allow_null=True, help_text="Nulo en los documentos de la solicitud."
    )
    document_type = CompletenessDocumentTypeSerializer(source="*")
    # `label` choca con el atributo `Field.label` de los stubs de DRF; como en
    # `CatalogItemRefSerializer`, el campo de la API se llama así.
    label = serializers.CharField()  # type: ignore[assignment]
    status = serializers.ChoiceField(choices=SlotStatus.choices)
    alternative_group_code = serializers.CharField(allow_null=True)
    expires_at = serializers.DateField(allow_null=True)
    complete = serializers.BooleanField(
        help_text="Cuenta como cumplido. En un grupo alternativo, si el grupo está cumplido."
    )


class CompletenessDocumentsSerializer(serializers.Serializer):
    verified = serializers.BooleanField()
    required_total = serializers.IntegerField(
        help_text="Obligatorios; un grupo alternativo cuenta como uno."
    )
    completed_total = serializers.IntegerField()
    message = serializers.CharField()
    slots = CompletenessDocumentSlotSerializer(
        many=True, help_text="Solo los slots vigentes y obligatorios."
    )


class CompletenessSerializer(serializers.Serializer):
    percentage = serializers.IntegerField(
        help_text="Promedio, entero hacia abajo, de `data_percentage` y `documents_percentage`."
    )
    data_percentage = serializers.IntegerField(help_text="Ítems de datos completos.")
    documents_percentage = serializers.IntegerField(
        help_text="Obligatorios cumplidos sobre obligatorios; 0 si no hay obligatorios."
    )
    ready_to_file = serializers.BooleanField(
        help_text="La guarda de `READY_TO_FILE` no tiene problemas."
    )
    ready_to_file_problems = ErrorDetailSerializer(
        many=True,
        help_text="Los mismos `details` que daría el `422 APPLICATION_NOT_READY`.",
    )
    items = CompletenessItemSerializer(many=True)
    documents = CompletenessDocumentsSerializer()
