"""DTO del portal para los datos personales, los perfiles financieros y los ingresos.

Las salidas son propias del portal: sin notas, sin el documento completo y sin datos de
auditoría. Las entradas del perfil y de los ingresos reutilizan los validadores
internos, para que las reglas no se separen; los ingresos del comprador no aceptan
``notes``, que es texto del asesor.
"""

from datetime import date
from typing import Any

from rest_framework import serializers

from apps.applications.models import ApplicationParticipant, FinancialProfile, IncomeSource
from apps.applications.serializers import (
    FinancialProfileInputSerializer,
    IncomeSourceCreateSerializer,
    IncomeSourceUpdateSerializer,
)
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.models import Client, ClientAddress
from apps.crm.validators import mask_document_number
from apps.documents.models import ParticipantRole
from config.serializers import StrictSerializer
from config.validators import validate_e164_phone

MAX_ADDRESSES = 10

# --- Datos personales -------------------------------------------------------------------


class BuyerAddressSerializer(serializers.ModelSerializer):
    address_type = CatalogItemRefSerializer(source="address_type_item", read_only=True)
    city = CatalogItemRefSerializer(source="city_item", read_only=True)

    class Meta:
        model = ClientAddress
        fields = ["id", "address_type", "city", "line1", "line2", "postal_code", "is_primary"]
        read_only_fields = fields


class BuyerProfileSerializer(serializers.ModelSerializer):
    """Datos del titular. El documento va enmascarado: si el enlace se filtra, no lo expone."""

    full_name = serializers.CharField(read_only=True)
    document_type = CatalogItemRefSerializer(source="document_type_item", read_only=True)
    document_number = serializers.SerializerMethodField()
    addresses = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "first_names",
            "last_names",
            "full_name",
            "document_type",
            "document_number",
            "birth_date",
            "email",
            "phone",
            "addresses",
            "updated_at",
        ]
        read_only_fields = fields

    def get_document_number(self, client: Client) -> str:
        return mask_document_number(client.document_number)

    def get_addresses(self, client: Client) -> list[dict[str, Any]]:
        addresses = self.context["addresses"]
        return [dict(item) for item in BuyerAddressSerializer(addresses, many=True).data]


class BuyerAddressInputSerializer(StrictSerializer):
    id = serializers.UUIDField(required=False)
    address_type_code = CatalogItemCodeField(catalog_code="address_type")
    city_code = CatalogItemCodeField(catalog_code="municipality")
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    is_primary = serializers.BooleanField(required=False, default=False)


class BuyerProfileUpdateSerializer(StrictSerializer):
    """``PATCH``: solo cambia lo que llega. ``addresses`` reemplaza la lista completa."""

    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    addresses = serializers.ListField(
        child=BuyerAddressInputSerializer(), required=False, max_length=MAX_ADDRESSES
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_phone(self, value: str) -> str:
        return validate_e164_phone(value)

    def validate_birth_date(self, value: date | None) -> date | None:
        if value is not None and value >= date.today():
            raise serializers.ValidationError("La fecha de nacimiento debe ser anterior a hoy.")
        return value

    def contact_changes(self) -> dict[str, Any]:
        return {
            field: value for field, value in self.validated_data.items() if field != "addresses"
        }

    def address_items(self) -> list[dict[str, Any]] | None:
        items = self.validated_data.get("addresses")
        if items is None:
            return None
        return [
            {
                "id": item.get("id"),
                "address_type_item": item["address_type_code"],
                "city_item": item["city_code"],
                "line1": item["line1"],
                "line2": item["line2"],
                "postal_code": item["postal_code"],
                "is_primary": item["is_primary"],
            }
            for item in items
        ]


# --- Participantes y perfil financiero --------------------------------------------------


class BuyerParticipantSummarySerializer(serializers.ModelSerializer):
    """Participante cuyo perfil e ingresos edita el comprador."""

    role = serializers.ChoiceField(choices=ParticipantRole.choices, read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    full_name = serializers.CharField(source="client.full_name", read_only=True)
    # Sin perfil, DRF devuelve `null`: la relación inversa ausente no es un error.
    financial_profile_id = serializers.UUIDField(
        source="financial_profile.pk", read_only=True, allow_null=True
    )
    data_confirmed_at = serializers.DateTimeField(
        source="financial_profile.data_confirmed_at", read_only=True, allow_null=True
    )

    class Meta:
        model = ApplicationParticipant
        fields = [
            "id",
            "role",
            "role_label",
            "full_name",
            "contributes_income",
            "financial_profile_id",
            "data_confirmed_at",
        ]
        read_only_fields = fields


class BuyerFinancialProfileSerializer(serializers.ModelSerializer):
    participant_id = serializers.UUIDField(read_only=True)
    employment_profile = CatalogItemRefSerializer(source="employment_profile_item", read_only=True)
    contract_type = CatalogItemRefSerializer(
        source="contract_type_item", read_only=True, allow_null=True
    )
    funds_origin = CatalogItemRefSerializer(
        source="funds_origin_item", read_only=True, allow_null=True
    )
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
            "updated_at",
        ]
        read_only_fields = fields


class BuyerFinancialProfileInputSerializer(FinancialProfileInputSerializer):
    """Mismas reglas que el ``PUT`` interno."""


# --- Fuentes de ingreso -----------------------------------------------------------------


class BuyerIncomeSourceSerializer(serializers.ModelSerializer):
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
            "updated_at",
        ]
        read_only_fields = fields


class BuyerIncomeSourceCreateSerializer(IncomeSourceCreateSerializer):
    # DRF quita del serializer un campo heredado que se declara como `None`.
    notes = None  # type: ignore[assignment]


class BuyerIncomeSourceUpdateSerializer(IncomeSourceUpdateSerializer):
    # Igual que en la creación: sin `notes`.
    notes = None  # type: ignore[assignment]
