"""Bancos, productos y reglas de demo (``seed_demo_data``, TAREA-brechas-3-demo).

- ``seed_bank_settings``: plazo de respuesta de Bancolombia (15 días), para que una
  radicación de la historia sin respuesta salga vencida (``is_response_overdue``), y un
  producto inactivo (vivienda VIS del Banco de Bogotá). Solo agrega: no cambia un plazo
  que ya tenga valor.
- ``seed_rules``: reglas del hipotecario de Bancolombia con más de una versión. "Plazo
  máximo": v1 (≤ 240 meses) publicada y reemplazada (inactiva), v2 (≤ 360) activa y v3
  (≤ 300) en borrador. "Relación monto / valor": v1 activa, solo advertencia. Se crean
  al final de la demo, así que no cambian la evaluación de las solicitudes sembradas, y
  las dos pasan con sus datos.

Pasa por los servicios. Marca: el código de cada producto o regla.
"""

from datetime import date

from django.utils import timezone

from apps.banking import services
from apps.banking.models import Bank, BankPolicyRule, BankProduct
from apps.catalogs.models import CatalogItem
from apps.identity.models import User

RESPONSE_DAYS = 15
INACTIVE_PRODUCT = ("BANCO_BOGOTA", "VIS_MORTGAGE")
TERM_RULE = "PLAZO_MAXIMO"
LTV_RULE = "RELACION_MONTO_VALOR"


def _term(months: int) -> dict[str, object]:
    return {"operator": "lte", "left": {"field": "financing.term_months"}, "right": months}


LTV_CONDITION = {
    "operator": "lte",
    "left": {
        "operator": "ratio",
        "numerator_field": "financing.requested_amount_cop",
        "denominator_field": "property.estimated_value_cop",
    },
    "right": 0.8,
}


def seed_bank_settings(admin: User) -> int:
    """Devuelve cuántos ajustes de bancos hizo (los productos nuevos los cuenta quien
    llama)."""
    changed = 0
    bancolombia = Bank.objects.get(code="BANCOLOMBIA")
    if bancolombia.filing_response_days is None:
        services.update_bank(bancolombia, {"filing_response_days": RESPONSE_DAYS})
        changed += 1
    bank_code, code = INACTIVE_PRODUCT
    bank = Bank.objects.get(code=bank_code)
    if not BankProduct.objects.filter(bank=bank, code=code).exists():
        product = services.create_product(
            {
                "bank": bank,
                "code": code,
                "name": "Crédito de vivienda VIS",
                "product_type_item": CatalogItem.objects.get(
                    catalog__code="bank_product_type", code="MORTGAGE"
                ),
                "valid_from": date(2025, 1, 1),
                "purposes": list(
                    CatalogItem.objects.filter(catalog__code="loan_purpose", code="PURCHASE_NEW")
                ),
            }
        )
        services.set_product_status(
            product, active=False, actor=admin, reason="El banco suspendió la línea VIS."
        )
    return changed


def _product() -> BankProduct:
    return BankProduct.objects.get(bank__code="BANCOLOMBIA", code="MORTGAGE")


def rules_exist() -> bool:
    return BankPolicyRule.objects.filter(bank_product=_product(), code=TERM_RULE).exists()


def seed_rules(admin: User) -> list[BankPolicyRule]:
    """Crea las dos reglas y sus versiones. Quien llama comprueba ``rules_exist``."""
    product = _product()
    since = timezone.now()
    term = services.create_rule(
        admin,
        {
            "bank_product": product,
            "purpose_item": None,
            "code": TERM_RULE,
            "severity": "BLOCKING",
            "condition": _term(240),
            "message": "El plazo no puede superar 20 años.",
            "valid_from": since,
        },
    )
    services.activate_rule(admin, term)
    second, _ = services.update_rule(
        admin,
        term,
        {"condition": _term(360), "message": "El plazo no puede superar 30 años."},
    )
    services.activate_rule(admin, second)
    draft, _ = services.update_rule(
        admin,
        second,
        {"condition": _term(300), "message": "El plazo no puede superar 25 años."},
    )
    ltv = services.create_rule(
        admin,
        {
            "bank_product": product,
            "purpose_item": None,
            "code": LTV_RULE,
            "severity": "WARNING",
            "condition": LTV_CONDITION,
            "message": "El monto supera el 80 % del valor del inmueble.",
            "valid_from": since,
        },
    )
    services.activate_rule(admin, ltv)
    return [term, second, draft, ltv]
