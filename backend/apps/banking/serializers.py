from typing import Any

from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.banking.models import Bank, BankPolicyRule, BankProduct, RuleSeverity
from apps.banking.rule_engine import Outcome
from apps.banking.services import active_purpose_items
from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.models import CatalogItem
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.partners.validators import normalize_nit
from config.serializers import StrictSerializer

MAX_AMOUNT_COP = 10**15  # Cabe en BIGINT con holgura.
MAX_TERM_MONTHS = 600  # 50 años; cabe en SMALLINT.
MAX_TEST_CASES = 20

bank_code_validator = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,49}$",
    "Usa mayúsculas, números y guion bajo, empezando por una letra (ej. BANCOLOMBIA).",
)
rule_code_validator = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,79}$",
    "Usa mayúsculas, números y guion bajo, empezando por una letra (ej. MAX_LTV_NEW_HOME).",
)


class BankingUserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="get_full_name")


def _normalize_tax_id(value: str) -> str:
    return normalize_nit(value) if value else ""


# --- Bancos -----------------------------------------------------------------------------


class BankRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    short_name = serializers.CharField(
        help_text="Nombre corto para listados; vacío si no tiene (se muestra `name`)."
    )


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            "id",
            "code",
            "name",
            "short_name",
            "tax_id",
            "status",
            "operational_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BankProductSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BankProduct
        fields = ["id", "code", "name", "status"]
        read_only_fields = fields


class BankDetailSerializer(BankSerializer):
    products = BankProductSummarySerializer(many=True, read_only=True)

    class Meta(BankSerializer.Meta):
        fields = [*BankSerializer.Meta.fields, "products"]
        read_only_fields = fields


class BankCreateSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50, validators=[bank_code_validator])
    name = serializers.CharField(max_length=180)
    short_name = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    tax_id = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    operational_notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_tax_id(self, value: str) -> str:
        return _normalize_tax_id(value)


class BankUpdateSerializer(StrictSerializer):
    """El código no se edita: es estable."""

    name = serializers.CharField(max_length=180, required=False)
    short_name = serializers.CharField(max_length=30, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=30, required=False, allow_blank=True)
    operational_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_tax_id(self, value: str) -> str:
        return _normalize_tax_id(value)


# --- Productos --------------------------------------------------------------------------


class BankProductSerializer(serializers.ModelSerializer):
    bank = BankRefSerializer(read_only=True)
    product_type = CatalogItemRefSerializer(source="product_type_item", read_only=True)
    purposes = serializers.SerializerMethodField()

    class Meta:
        model = BankProduct
        fields = [
            "id",
            "bank",
            "code",
            "name",
            "product_type",
            "status",
            "min_amount_cop",
            "max_amount_cop",
            "min_term_months",
            "max_term_months",
            "valid_from",
            "valid_to",
            "purposes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def _purpose_ref(item: CatalogItem) -> dict[str, str]:
        return {"code": item.code, "label": item.label}

    def get_purposes(self, obj: BankProduct) -> list[dict[str, str]]:
        """Finalidades activas: `[{"code": "PURCHASE_NEW", "label": "..."}]`."""
        return [self._purpose_ref(item) for item in active_purpose_items(obj)]


def _amount_field(**kwargs: Any) -> serializers.IntegerField:
    return serializers.IntegerField(min_value=0, max_value=MAX_AMOUNT_COP, **kwargs)


def _term_field(**kwargs: Any) -> serializers.IntegerField:
    return serializers.IntegerField(min_value=1, max_value=MAX_TERM_MONTHS, **kwargs)


def _unique_items(items: list[CatalogItem]) -> list[CatalogItem]:
    codes = [item.code for item in items]
    duplicated = sorted({code for code in codes if codes.count(code) > 1})
    if duplicated:
        raise serializers.ValidationError(f"Finalidades repetidas: {', '.join(duplicated)}.")
    return items


class _ProductFields(StrictSerializer):
    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "product_type_code" in data:
            data["product_type_item"] = data.pop("product_type_code")
        if "purpose_codes" in data:
            data["purposes"] = data.pop("purpose_codes")
        return data


class BankProductCreateSerializer(_ProductFields):
    bank_id = serializers.UUIDField()
    code = serializers.CharField(max_length=50, validators=[bank_code_validator])
    name = serializers.CharField(max_length=180)
    product_type_code = CatalogItemCodeField(catalog_code="bank_product_type")
    min_amount_cop = _amount_field(required=False, allow_null=True)
    max_amount_cop = _amount_field(required=False, allow_null=True)
    min_term_months = _term_field(required=False, allow_null=True)
    max_term_months = _term_field(required=False, allow_null=True)
    valid_from = serializers.DateField(required=False, help_text="Por defecto, hoy.")
    valid_to = serializers.DateField(required=False, allow_null=True)
    purpose_codes = serializers.ListField(
        child=CatalogItemCodeField(catalog_code="loan_purpose"), required=False, default=list
    )

    def validate_purpose_codes(self, value: list[CatalogItem]) -> list[CatalogItem]:
        return _unique_items(value)

    def validate_bank_id(self, value: Any) -> Bank:
        bank = Bank.objects.filter(pk=value).first()
        if bank is None:
            raise serializers.ValidationError("El banco no existe.")
        return bank

    def to_service_data(self) -> dict[str, Any]:
        data = super().to_service_data()
        data["bank"] = data.pop("bank_id")
        return data


class BankProductUpdateSerializer(_ProductFields):
    """El banco y el código no se editan."""

    name = serializers.CharField(max_length=180, required=False)
    product_type_code = CatalogItemCodeField(catalog_code="bank_product_type", required=False)
    min_amount_cop = _amount_field(required=False, allow_null=True)
    max_amount_cop = _amount_field(required=False, allow_null=True)
    min_term_months = _term_field(required=False, allow_null=True)
    max_term_months = _term_field(required=False, allow_null=True)
    valid_from = serializers.DateField(required=False)
    valid_to = serializers.DateField(required=False, allow_null=True)


class ProductPurposesSerializer(StrictSerializer):
    purpose_codes = serializers.ListField(
        child=CatalogItemCodeField(catalog_code="loan_purpose"), allow_empty=True
    )

    def validate_purpose_codes(self, value: list[CatalogItem]) -> list[CatalogItem]:
        return _unique_items(value)


# --- Reglas -----------------------------------------------------------------------------


class RuleProductRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    bank = BankRefSerializer()


class BankPolicyRuleSerializer(serializers.ModelSerializer):
    bank_product = RuleProductRefSerializer(read_only=True)
    purpose = CatalogItemRefSerializer(source="purpose_item", read_only=True, allow_null=True)
    created_by = BankingUserRefSerializer(read_only=True)
    condition = serializers.JSONField(read_only=True)

    class Meta:
        model = BankPolicyRule
        fields = [
            "id",
            "bank_product",
            "purpose",
            "code",
            "version",
            "severity",
            "condition",
            "message",
            "status",
            "valid_from",
            "valid_to",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class _RuleFields(StrictSerializer):
    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "purpose_code" in data:
            data["purpose_item"] = data.pop("purpose_code")
        return data


class BankPolicyRuleCreateSerializer(_RuleFields):
    bank_product_id = serializers.UUIDField()
    purpose_code = CatalogItemCodeField(
        catalog_code="loan_purpose",
        required=False,
        allow_null=True,
        default=None,
        help_text="Vacío: la regla aplica a todas las finalidades.",
    )
    code = serializers.CharField(max_length=80, validators=[rule_code_validator])
    severity = serializers.ChoiceField(choices=RuleSeverity.choices)
    condition = serializers.JSONField(help_text="Condición declarativa (sección 23.3).")
    message = serializers.CharField(max_length=1000)
    valid_from = serializers.DateTimeField(required=False, help_text="Por defecto, ahora.")
    valid_to = serializers.DateTimeField(required=False, allow_null=True)

    def validate_bank_product_id(self, value: Any) -> BankProduct:
        product = BankProduct.objects.filter(pk=value).first()
        if product is None:
            raise serializers.ValidationError("El producto no existe.")
        return product

    def to_service_data(self) -> dict[str, Any]:
        data = super().to_service_data()
        data["bank_product"] = data.pop("bank_product_id")
        return data


class BankPolicyRuleUpdateSerializer(_RuleFields):
    """El producto y el código no se editan: identifican la regla."""

    purpose_code = CatalogItemCodeField(
        catalog_code="loan_purpose", required=False, allow_null=True
    )
    severity = serializers.ChoiceField(choices=RuleSeverity.choices, required=False)
    condition = serializers.JSONField(required=False)
    message = serializers.CharField(max_length=1000, required=False)
    valid_from = serializers.DateTimeField(required=False)
    valid_to = serializers.DateTimeField(required=False, allow_null=True)


class RuleTestCaseSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    expected = serializers.ChoiceField(
        choices=[(outcome.value, outcome.value) for outcome in Outcome],
        required=False,
        allow_null=True,
        default=None,
    )

    def get_fields(self) -> dict[str, serializers.Field]:
        # `context` se declara aquí y no como atributo de clase porque ese nombre
        # choca con el atributo `Field.context` de DRF.
        fields = super().get_fields()
        fields["context"] = serializers.DictField(
            help_text='Datos del caso, p. ej. `{"financing": {"requested_amount_cop": 1}}`.'
        )
        return fields


class RuleTestRequestSerializer(StrictSerializer):
    cases = serializers.ListField(
        child=RuleTestCaseSerializer(), min_length=1, max_length=MAX_TEST_CASES
    )


class RuleTestResultSerializer(serializers.Serializer):
    name = serializers.CharField()
    outcome = serializers.ChoiceField(choices=[outcome.value for outcome in Outcome])
    unresolved_fields = serializers.ListField(child=serializers.CharField())
    expected = serializers.CharField(allow_null=True)
    matches_expected = serializers.BooleanField(allow_null=True)


class RuleVersionRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    version = serializers.IntegerField()


class RuleTestResponseSerializer(serializers.Serializer):
    rule = RuleVersionRefSerializer()
    results = RuleTestResultSerializer(many=True)
