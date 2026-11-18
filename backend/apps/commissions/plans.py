"""Planes de comisión (Parte 1): alta, edición, cierre, solapamiento y "en uso".

- **Vigencia:** ``[valid_from, valid_until)``; ``valid_until`` nulo es vigente sin fin.
- **Solapamiento:** dos planes del mismo producto no pueden compartir un día. Se valida
  dentro de la transacción, con la fila del producto bloqueada (``select_for_update``),
  así que dos altas simultáneas del mismo producto se serializan.
- **En uso:** un plan con alguna liquidación (vigente o anulada) no se edita
  (``409 COMMISSION_PLAN_IN_USE``): se cierra y se crea otro. Cerrar sí se permite.
- Cada cambio sube ``version`` (``If-Match`` en ``PATCH``).
"""

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from rest_framework.exceptions import ValidationError

from apps.applications.concurrency import ensure_version
from apps.banking.models import BankProduct
from apps.commissions.exceptions import CommissionPlanInUse, CommissionPlanOverlap
from apps.commissions.models import HUNDRED, ZERO, CommissionPlan, CommissionSettlement
from apps.identity.models import User

EDITABLE_FIELDS = (
    "rate_pct",
    "advisor_share_pct",
    "broker_share_pct",
    "valid_from",
    "valid_until",
    "notes",
)


def plans_queryset() -> QuerySet[CommissionPlan]:
    """Planes con lo que muestra la respuesta y ``in_use`` anotado: sin consultas por fila."""
    used = CommissionSettlement.objects.filter(plan=OuterRef("pk"))
    return CommissionPlan.objects.select_related("bank_product__bank", "created_by").annotate(
        in_use=Exists(used)
    )


def valid_on(day: date) -> Q:
    """Planes vigentes en ``day``."""
    return Q(valid_from__lte=day) & (Q(valid_until__isnull=True) | Q(valid_until__gt=day))


def overlap_condition(valid_from: date, valid_until: date | None) -> Q:
    """Planes cuya vigencia comparte al menos un día con ``[valid_from, valid_until)``."""
    condition = Q(valid_until__isnull=True) | Q(valid_until__gt=valid_from)
    if valid_until is not None:
        condition &= Q(valid_from__lt=valid_until)
    return condition


def validate_terms(
    *,
    rate_pct: Decimal,
    advisor_share_pct: Decimal,
    broker_share_pct: Decimal,
    valid_from: date,
    valid_until: date | None,
) -> None:
    """Las reglas de los ``CHECK``, como ``400`` con el campo."""
    errors: dict[str, list[str]] = {}
    if not ZERO < rate_pct <= HUNDRED:
        errors["rate_pct"] = ["Debe ser mayor que 0 y como mucho 100."]
    if broker_share_pct < ZERO:
        errors["broker_share_pct"] = ["No puede ser negativo."]
    elif advisor_share_pct + broker_share_pct != HUNDRED:
        errors["advisor_share_pct"] = ["La porción del asesor y la del broker deben sumar 100."]
    elif advisor_share_pct <= broker_share_pct:
        errors["advisor_share_pct"] = ["El asesor siempre lleva la porción mayor."]
    if valid_until is not None and valid_until <= valid_from:
        errors["valid_until"] = ["Debe ser posterior a valid_from."]
    if errors:
        raise ValidationError(errors)


def _ensure_no_overlap(
    product: BankProduct,
    valid_from: date,
    valid_until: date | None,
    *,
    exclude: CommissionPlan | None = None,
) -> None:
    others = CommissionPlan.objects.filter(bank_product=product).filter(
        overlap_condition(valid_from, valid_until)
    )
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if others.exists():
        raise CommissionPlanOverlap()


def _lock_product(product_id: Any) -> BankProduct:
    return BankProduct.objects.select_for_update().get(pk=product_id)


def create_plan(actor: User, data: dict[str, Any]) -> CommissionPlan:
    validate_terms(
        rate_pct=data["rate_pct"],
        advisor_share_pct=data["advisor_share_pct"],
        broker_share_pct=data["broker_share_pct"],
        valid_from=data["valid_from"],
        valid_until=data.get("valid_until"),
    )
    with transaction.atomic():
        product = _lock_product(data["bank_product"].pk)
        _ensure_no_overlap(product, data["valid_from"], data.get("valid_until"))
        plan = CommissionPlan.objects.create(
            bank_product=product,
            rate_pct=data["rate_pct"],
            advisor_share_pct=data["advisor_share_pct"],
            broker_share_pct=data["broker_share_pct"],
            valid_from=data["valid_from"],
            valid_until=data.get("valid_until"),
            notes=data.get("notes", ""),
            created_by=actor,
        )
    return plan


def is_in_use(plan: CommissionPlan) -> bool:
    return CommissionSettlement.objects.filter(plan=plan).exists()


def update_plan(
    plan: CommissionPlan, changes: dict[str, Any], *, expected_version: int
) -> CommissionPlan:
    """Edita un plan que ninguna liquidación usó. ``changes`` solo trae los campos enviados.
    Otra versión: ``409 STALE_VERSION``."""
    with transaction.atomic():
        _lock_product(plan.bank_product_id)
        locked = CommissionPlan.objects.select_for_update().get(pk=plan.pk)
        ensure_version(locked.version, expected_version)
        if is_in_use(locked):
            raise CommissionPlanInUse()
        fields = [field for field in EDITABLE_FIELDS if field in changes]
        for field in fields:
            setattr(locked, field, changes[field])
        validate_terms(
            rate_pct=locked.rate_pct,
            advisor_share_pct=locked.advisor_share_pct,
            broker_share_pct=locked.broker_share_pct,
            valid_from=locked.valid_from,
            valid_until=locked.valid_until,
        )
        _ensure_no_overlap(
            locked.bank_product, locked.valid_from, locked.valid_until, exclude=locked
        )
        if fields:
            locked.version += 1
            locked.save(update_fields=[*fields, "version", "updated_at"])
    return locked


def close_plan(plan: CommissionPlan, valid_until: date) -> CommissionPlan:
    """Fija el fin de vigencia; se permite también en un plan en uso. Solo adelanta el fin:
    un plan ya cerrado no se alarga (eso podría solaparse)."""
    with transaction.atomic():
        locked = CommissionPlan.objects.select_for_update().get(pk=plan.pk)
        if valid_until <= locked.valid_from:
            raise ValidationError({"valid_until": ["Debe ser posterior a valid_from."]})
        if locked.valid_until is not None and valid_until > locked.valid_until:
            raise ValidationError(
                {"valid_until": ["El plan ya termina antes: cerrar solo adelanta el fin."]}
            )
        locked.valid_until = valid_until
        locked.version += 1
        locked.save(update_fields=["valid_until", "version", "updated_at"])
    return locked
