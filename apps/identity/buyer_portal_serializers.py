"""DTO del portal del comprador (API §8).

No reutilizan los serializers administrativos: solo exponen lo que el comprador puede
ver de su propio proceso. Las referencias compactas (catálogo, producto) sí se
reutilizan, para que OpenAPI no tenga dos componentes con el mismo nombre.
"""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancingPreference,
    ParticipantRole,
    Property,
)
from apps.applications.serializers import BankProductRefSerializer, NamedRefSerializer
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.catalogs.workflow import ApplicationStatus
from apps.identity import buyer_portal, consents
from apps.identity.models import BuyerSession, ConsentAction, ConsentDefinition, ConsentRecord
from config.serializers import StrictSerializer

# --- Consumo y sesión -------------------------------------------------------------------


class BuyerAccessConsumeSerializer(StrictSerializer):
    token = serializers.CharField(max_length=512, trim_whitespace=False)


class BuyerRefSerializer(serializers.Serializer):
    display_name = serializers.CharField(source="full_name")


class BuyerApplicationRefSerializer(serializers.ModelSerializer):
    public_status = serializers.ChoiceField(source="status", choices=ApplicationStatus.choices)
    public_status_label = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)
    is_closed = serializers.BooleanField(source="is_terminal", read_only=True)

    class Meta:
        model = CreditApplication
        fields = ["id", "code", "public_status", "public_status_label", "is_editable", "is_closed"]
        read_only_fields = fields

    def get_public_status_label(self, application: CreditApplication) -> str:
        return buyer_portal.public_status_label(application.status)


class BuyerAccessConsumeResponseSerializer(serializers.Serializer):
    buyer = BuyerRefSerializer(source="session.client")
    application = BuyerApplicationRefSerializer(source="session.application")
    session_expires_at = serializers.DateTimeField(source="session.expires_at")


class BuyerSessionInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerSession
        fields = ["id", "created_at", "expires_at"]
        read_only_fields = fields


class BuyerSessionResponseSerializer(serializers.Serializer):
    session = BuyerSessionInfoSerializer(source="*")
    buyer = BuyerRefSerializer(source="client")
    application = BuyerApplicationRefSerializer()
    # Códigos de los consentimientos obligatorios que faltan; bloquean las escrituras.
    pending_consents = serializers.SerializerMethodField()

    def get_pending_consents(self, session: BuyerSession) -> list[str]:
        return [definition.code for definition in consents.missing_consents(session)]


# --- Proceso y solicitud ----------------------------------------------------------------


class BuyerProcessSerializer(BuyerApplicationRefSerializer):
    """Resumen del proceso: estado público, siguiente acción y progreso."""

    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True)
    next_action = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta(BuyerApplicationRefSerializer.Meta):
        fields = [
            *BuyerApplicationRefSerializer.Meta.fields,
            "purpose",
            "next_action",
            "progress_percentage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_next_action(self, application: CreditApplication) -> str:
        return buyer_portal.next_action(application.status)

    def get_progress_percentage(self, application: CreditApplication) -> int:
        return self._progress(application).percentage

    def _progress(self, application: CreditApplication) -> buyer_portal.BuyerProgress:
        # Se calcula una sola vez por solicitud, aunque lo usen dos campos.
        cache: dict[Any, buyer_portal.BuyerProgress] = self.context.setdefault("_progress", {})
        if application.pk not in cache:
            cache[application.pk] = buyer_portal.buyer_progress(application)
        return cache[application.pk]


class BuyerProgressItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    complete = serializers.BooleanField()
    message = serializers.CharField()
    participant_id = serializers.UUIDField(allow_null=True)


class BuyerProgressSerializer(serializers.Serializer):
    percentage = serializers.IntegerField()
    items = BuyerProgressItemSerializer(many=True)


class BuyerParticipantSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ParticipantRole.choices, read_only=True)
    full_name = serializers.CharField(source="client.full_name", read_only=True)

    class Meta:
        model = ApplicationParticipant
        fields = ["id", "role", "full_name", "contributes_income"]
        read_only_fields = fields


class BuyerPropertySerializer(serializers.ModelSerializer):
    project = NamedRefSerializer(read_only=True, allow_null=True)
    property_type = CatalogItemRefSerializer(source="property_type_item", read_only=True)
    condition = CatalogItemRefSerializer(source="condition_item", read_only=True)
    city = CatalogItemRefSerializer(source="city_item", read_only=True)

    class Meta:
        model = Property
        fields = [
            "project",
            "property_type",
            "condition",
            "city",
            "address",
            "unit_reference",
            "estimated_value_cop",
            "is_owned_by_applicant",
            "updated_at",
        ]
        read_only_fields = fields


class BuyerFinancingSerializer(serializers.ModelSerializer):
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
            "updated_at",
        ]
        read_only_fields = fields


class BuyerApplicationDetailSerializer(BuyerProcessSerializer):
    """Solicitud vista por el comprador. La versión también viaja en ``ETag``."""

    progress = serializers.SerializerMethodField()
    participants = BuyerParticipantSerializer(
        source="active_participants", many=True, read_only=True
    )
    property = BuyerPropertySerializer(source="financed_property", read_only=True, allow_null=True)
    financing = BuyerFinancingSerializer(read_only=True, allow_null=True)

    class Meta(BuyerProcessSerializer.Meta):
        fields = [
            *BuyerProcessSerializer.Meta.fields,
            "version",
            "progress",
            "participants",
            "property",
            "financing",
        ]
        read_only_fields = fields

    @extend_schema_field(BuyerProgressSerializer)
    def get_progress(self, application: CreditApplication) -> dict[str, Any]:
        return dict(BuyerProgressSerializer(self._progress(application)).data)


# --- Consentimientos --------------------------------------------------------------------


class BuyerConsentSerializer(serializers.Serializer):
    """Versión vigente de un consentimiento y su estado para el comprador."""

    id = serializers.UUIDField(source="definition.pk")
    code = serializers.CharField(source="definition.code")
    version = serializers.IntegerField(source="definition.version")
    title = serializers.CharField(source="definition.title")
    body = serializers.CharField(source="definition.body")
    content_hash = serializers.CharField(source="definition.content_hash")
    effective_from = serializers.DateTimeField(source="definition.effective_from")
    # El metaclass de DRF retira los campos declarados de la clase, así que no pisa
    # `Field.required` en tiempo de ejecución; mypy no lo sabe.
    required = serializers.BooleanField()  # type: ignore[assignment]
    status = serializers.ChoiceField(choices=consents.ConsentStatus.choices)
    accepted_at = serializers.DateTimeField(allow_null=True)


class BuyerConsentListSerializer(serializers.Serializer):
    items = BuyerConsentSerializer(many=True)
    pending_required = serializers.ListField(child=serializers.CharField())


class BuyerConsentActionSerializer(StrictSerializer):
    consent_definition_id = serializers.PrimaryKeyRelatedField(
        queryset=ConsentDefinition.objects.all()
    )
    action = serializers.ChoiceField(choices=ConsentAction.choices)


class BuyerConsentRecordSerializer(serializers.ModelSerializer):
    consent_definition_id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(source="consent_definition.code", read_only=True)
    version = serializers.IntegerField(source="consent_definition.version", read_only=True)
    action = serializers.ChoiceField(choices=ConsentAction.choices, read_only=True)

    class Meta:
        model = ConsentRecord
        fields = ["id", "consent_definition_id", "code", "version", "action", "created_at"]
        read_only_fields = fields
