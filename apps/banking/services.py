"""Casos de uso del módulo banking: bancos, productos, finalidades y reglas operativas.

Acceso (sección 8.6 de los requerimientos):

- ``banks.read`` y ``bank_rules.read``: ``ADMIN`` y ``ADVISOR``.
- Crear y editar bancos, productos y reglas, y publicar reglas: solo ``ADMIN``.
- ``INDEPENDENT_BROKER`` y ``CONSTRUCTION_PARTNER`` no consultan esta configuración.

No hay alcance por fila: quien tiene el permiso ve toda la configuración. La elección
de banco dentro de una solicitud no pasa por ``/banks``: el paso 8 la resolverá en
``/applications/{id}/eligible-bank-products`` con ``available_products`` y
``evaluate_rules``.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max, Prefetch, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.banking.exceptions import RuleConditionInvalid, RuleDraftExists, RuleExpired
from apps.banking.models import (
    Bank,
    BankPolicyRule,
    BankProduct,
    BankProductPurpose,
    BankStatus,
    RuleStatus,
)
from apps.banking.rule_engine import (
    ConditionError,
    Outcome,
    evaluate_condition,
    validate_condition,
    validate_context,
)
from apps.banking.signals import (
    bank_policy_rule_status_changed,
    bank_product_status_changed,
    bank_status_changed,
)
from apps.catalogs.exceptions import DuplicateCode, InvalidStateTransition
from apps.catalogs.models import CatalogItem
from apps.catalogs.services import today
from apps.identity.models import User

logger = logging.getLogger(__name__)


def _save_changes(instance: Bank | BankProduct, changes: Mapping[str, Any]) -> None:
    for name, value in changes.items():
        setattr(instance, name, value)
    instance.save(update_fields=[*changes, "updated_at"])


def _status_target(active: bool) -> str:
    return BankStatus.ACTIVE if active else BankStatus.INACTIVE


# --------------------------------------------------------------------------------------
# Bancos
# --------------------------------------------------------------------------------------


def banks_queryset() -> QuerySet[Bank]:
    return Bank.objects.all()


def create_bank(data: dict[str, Any]) -> Bank:
    try:
        with transaction.atomic():
            return Bank.objects.create(**data)
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe un banco con ese código.") from exc


def update_bank(bank: Bank, changes: dict[str, Any]) -> Bank:
    if changes:
        _save_changes(bank, changes)
    return bank


def set_bank_status(bank: Bank, *, active: bool, actor: User, reason: str = "") -> Bank:
    """Desactivar un banco lo saca de nuevas solicitudes; no altera el historial."""
    target = _status_target(active)
    previous = bank.status
    if previous == target:
        return bank
    bank.status = target
    bank.save(update_fields=["status", "updated_at"])
    logger.info(
        "Banco %s: %s → %s por %s. Motivo: %s", bank.pk, previous, target, actor.pk, reason or "-"
    )
    bank_status_changed.send(
        sender=Bank, bank=bank, from_status=previous, to_status=target, actor=actor, reason=reason
    )
    return bank


# --------------------------------------------------------------------------------------
# Productos y finalidades
# --------------------------------------------------------------------------------------


def products_queryset() -> QuerySet[BankProduct]:
    active_purposes = BankProductPurpose.objects.filter(is_active=True).select_related(
        "purpose_item"
    )
    return BankProduct.objects.select_related("bank", "product_type_item").prefetch_related(
        Prefetch("purposes", queryset=active_purposes, to_attr="active_purposes")
    )


def active_purpose_items(product: BankProduct) -> list[CatalogItem]:
    """Finalidades activas del producto, usando el prefetch si está disponible."""
    rows: list[BankProductPurpose] | None = getattr(product, "active_purposes", None)
    if rows is None:
        rows = list(product.purposes.filter(is_active=True).select_related("purpose_item"))
    return [row.purpose_item for row in rows]


def _validate_product_ranges(values: Mapping[str, Any]) -> None:
    errors: dict[str, list[str]] = {}
    pairs = (
        ("min_amount_cop", "max_amount_cop"),
        ("min_term_months", "max_term_months"),
        ("valid_from", "valid_to"),
    )
    for low, high in pairs:
        if values.get(low) is not None and values.get(high) is not None:
            if values[high] < values[low]:
                errors[high] = [f"Debe ser mayor o igual que {low}."]
    if errors:
        raise ValidationError(errors)


def _set_purposes(product: BankProduct, purposes: list[CatalogItem]) -> None:
    wanted = {purpose.pk for purpose in purposes}
    existing = {row.purpose_item_id: row for row in product.purposes.all()}
    for purpose_id, row in existing.items():
        should_be_active = purpose_id in wanted
        if row.is_active != should_be_active:
            row.is_active = should_be_active
            row.save(update_fields=["is_active"])
    BankProductPurpose.objects.bulk_create(
        BankProductPurpose(bank_product=product, purpose_item=purpose)
        for purpose in purposes
        if purpose.pk not in existing
    )


def create_product(data: dict[str, Any]) -> BankProduct:
    purposes: list[CatalogItem] = data.pop("purposes", [])
    _validate_product_ranges(data)
    try:
        with transaction.atomic():
            product = BankProduct.objects.create(**data)
            _set_purposes(product, purposes)
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe un producto con ese código en el banco.") from exc
    return product


_PRODUCT_RANGE_FIELDS = (
    "min_amount_cop",
    "max_amount_cop",
    "min_term_months",
    "max_term_months",
    "valid_from",
    "valid_to",
)


def update_product(product: BankProduct, changes: dict[str, Any]) -> BankProduct:
    if not changes:
        return product
    current = {name: getattr(product, name) for name in _PRODUCT_RANGE_FIELDS}
    _validate_product_ranges({**current, **changes})
    _save_changes(product, changes)
    return product


def set_product_status(
    product: BankProduct, *, active: bool, actor: User, reason: str = ""
) -> BankProduct:
    target = _status_target(active)
    previous = product.status
    if previous == target:
        return product
    product.status = target
    product.save(update_fields=["status", "updated_at"])
    logger.info(
        "Producto %s: %s → %s por %s. Motivo: %s",
        product.pk,
        previous,
        target,
        actor.pk,
        reason or "-",
    )
    bank_product_status_changed.send(
        sender=BankProduct,
        product=product,
        from_status=previous,
        to_status=target,
        actor=actor,
        reason=reason,
    )
    return product


def set_product_purposes(product: BankProduct, purposes: list[CatalogItem]) -> BankProduct:
    """Reemplaza las finalidades admitidas. Las que salen se desactivan, no se borran."""
    with transaction.atomic():
        BankProduct.objects.select_for_update().filter(pk=product.pk).first()
        _set_purposes(product, purposes)
        product.save(update_fields=["updated_at"])
    return product


def available_products(
    *, on: date | None = None, purpose: CatalogItem | None = None
) -> QuerySet[BankProduct]:
    """Productos que pueden elegirse hoy (o en ``on``): banco y producto activos y vigentes.

    Con ``purpose``, solo los que admiten esa finalidad. Lo usará el paso 8.
    """
    day = on or today()
    products = products_queryset().filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=day),
        status=BankStatus.ACTIVE,
        bank__status=BankStatus.ACTIVE,
        valid_from__lte=day,
    )
    if purpose is not None:
        products = products.filter(
            purposes__purpose_item=purpose, purposes__is_active=True
        ).distinct()
    return products


# --------------------------------------------------------------------------------------
# Reglas operativas
# --------------------------------------------------------------------------------------


def rules_queryset() -> QuerySet[BankPolicyRule]:
    return BankPolicyRule.objects.select_related("bank_product__bank", "purpose_item", "created_by")


def _check_condition(condition: Any) -> None:
    try:
        validate_condition(condition)
    except ConditionError as exc:
        raise ValidationError({exc.path: [exc.message]}) from exc


def _check_rule_validity(valid_from: datetime, valid_to: datetime | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise ValidationError({"valid_to": ["Debe ser mayor o igual que valid_from."]})


def _lock_product(product_id: uuid.UUID) -> None:
    """Serializa los cambios de reglas de un producto (versiones y publicación)."""
    BankProduct.objects.select_for_update().filter(pk=product_id).first()


def _family(rule: BankPolicyRule) -> QuerySet[BankPolicyRule]:
    """Todas las versiones de la misma regla lógica."""
    return BankPolicyRule.objects.filter(bank_product_id=rule.bank_product_id, code=rule.code)


def create_rule(actor: User, data: dict[str, Any]) -> BankPolicyRule:
    """Crea la versión 1 de una regla, en borrador (sección 23.3)."""
    data.setdefault("valid_from", timezone.now())
    _check_condition(data["condition"])
    _check_rule_validity(data["valid_from"], data.get("valid_to"))
    product: BankProduct = data["bank_product"]
    try:
        with transaction.atomic():
            _lock_product(product.pk)
            if BankPolicyRule.objects.filter(bank_product=product, code=data["code"]).exists():
                raise DuplicateCode(
                    "Ya existe una regla con ese código en el producto. "
                    "Edítala para crear una versión nueva."
                )
            return BankPolicyRule.objects.create(
                **data, version=1, status=RuleStatus.DRAFT, created_by=actor
            )
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe una regla con ese código en el producto.") from exc


_EDITABLE_RULE_FIELDS = (
    "purpose_item",
    "severity",
    "condition",
    "message",
    "valid_from",
    "valid_to",
)


def _draft_exists_error(draft: BankPolicyRule) -> RuleDraftExists:
    return RuleDraftExists(
        details=[
            {
                "field": None,
                "code": "EXISTING_DRAFT",
                "message": f"Edita el borrador v{draft.version}.",
                "resource_id": str(draft.pk),
            }
        ]
    )


def update_rule(
    actor: User, rule: BankPolicyRule, changes: dict[str, Any]
) -> tuple[BankPolicyRule, bool]:
    """Edita un borrador o, sobre una versión publicada, crea un borrador nuevo.

    Devuelve la regla resultante y si se creó una versión. La versión publicada
    (``ACTIVE`` o ``INACTIVE``) nunca se modifica. Solo existe un borrador por
    regla: si ya hay uno, responde ``409 RULE_DRAFT_EXISTS`` con su id.
    """
    if not changes:
        return rule, False
    if "condition" in changes:
        _check_condition(changes["condition"])
    _check_rule_validity(
        changes.get("valid_from", rule.valid_from), changes.get("valid_to", rule.valid_to)
    )

    with transaction.atomic():
        _lock_product(rule.bank_product_id)
        rule.refresh_from_db()
        if rule.status == RuleStatus.DRAFT:
            for name, value in changes.items():
                setattr(rule, name, value)
            rule.save(update_fields=[*changes, "updated_at"])
            return rule, False

        draft = _family(rule).filter(status=RuleStatus.DRAFT).first()
        if draft is not None:
            raise _draft_exists_error(draft)
        latest = _family(rule).aggregate(latest=Max("version"))["latest"]
        values = {name: getattr(rule, name) for name in _EDITABLE_RULE_FIELDS}
        values.update(changes)
        new_version = BankPolicyRule.objects.create(
            bank_product_id=rule.bank_product_id,
            code=rule.code,
            version=latest + 1,
            status=RuleStatus.DRAFT,
            created_by=actor,
            **values,
        )
    logger.info(
        "Regla %s: borrador v%s creado desde v%s por %s",
        rule.code,
        new_version.version,
        rule.version,
        actor.pk,
    )
    return new_version, True


def _notify_rule_status(rule: BankPolicyRule, from_status: str, actor: User) -> None:
    logger.info(
        "Regla %s v%s: %s → %s por %s", rule.code, rule.version, from_status, rule.status, actor.pk
    )
    bank_policy_rule_status_changed.send(
        sender=BankPolicyRule,
        rule=rule,
        from_status=from_status,
        to_status=rule.status,
        actor=actor,
    )


def activate_rule(actor: User, rule: BankPolicyRule) -> BankPolicyRule:
    """Publica una versión. La versión ``ACTIVE`` anterior de la regla pasa a ``INACTIVE``.

    Antes de publicar se vuelve a validar la condición contra la lista blanca actual.
    """
    with transaction.atomic():
        _lock_product(rule.bank_product_id)
        rule.refresh_from_db()
        if rule.status == RuleStatus.ACTIVE:
            return rule
        try:
            validate_condition(rule.condition)
        except ConditionError as exc:
            raise RuleConditionInvalid(
                details=[{"field": exc.path, "code": "INVALID_CONDITION", "message": exc.message}]
            ) from exc
        if rule.valid_to is not None and rule.valid_to < timezone.now():
            raise RuleExpired()

        previous = _family(rule).filter(status=RuleStatus.ACTIVE).first()
        if previous is not None:
            previous.status = RuleStatus.INACTIVE
            previous.save(update_fields=["status", "updated_at"])
        from_status = rule.status
        rule.status = RuleStatus.ACTIVE
        rule.save(update_fields=["status", "updated_at"])

    if previous is not None:
        _notify_rule_status(previous, RuleStatus.ACTIVE, actor)
    _notify_rule_status(rule, from_status, actor)
    return rule


def deactivate_rule(actor: User, rule: BankPolicyRule) -> BankPolicyRule:
    """Detiene la aplicación futura de la versión publicada."""
    with transaction.atomic():
        _lock_product(rule.bank_product_id)
        rule.refresh_from_db()
        if rule.status == RuleStatus.INACTIVE:
            return rule
        if rule.status == RuleStatus.DRAFT:
            raise InvalidStateTransition("Un borrador no está publicado: no se puede desactivar.")
        rule.status = RuleStatus.INACTIVE
        rule.save(update_fields=["status", "updated_at"])
    _notify_rule_status(rule, RuleStatus.ACTIVE, actor)
    return rule


def rule_versions(rule: BankPolicyRule) -> QuerySet[BankPolicyRule]:
    return rules_queryset().filter(bank_product_id=rule.bank_product_id, code=rule.code)


# --------------------------------------------------------------------------------------
# Evaluación
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleResult:
    rule_id: uuid.UUID
    code: str
    version: int
    severity: str
    message: str
    outcome: Outcome
    unresolved_fields: list[str] = field(default_factory=list)


def applicable_rules(
    product: BankProduct, *, purpose: CatalogItem | None = None, at: datetime | None = None
) -> QuerySet[BankPolicyRule]:
    """Versiones publicadas y vigentes en ``at`` para el producto y la finalidad.

    Una regla sin finalidad aplica a todas.
    """
    moment = at or timezone.now()
    purpose_filter = Q(purpose_item__isnull=True)
    if purpose is not None:
        purpose_filter |= Q(purpose_item=purpose)
    return BankPolicyRule.objects.filter(
        purpose_filter,
        Q(valid_to__isnull=True) | Q(valid_to__gte=moment),
        bank_product=product,
        status=RuleStatus.ACTIVE,
        valid_from__lte=moment,
    ).order_by("code")


def evaluate_rule(rule: BankPolicyRule, context: Mapping[str, Any]) -> RuleResult:
    result = evaluate_condition(rule.condition, context)
    return RuleResult(
        rule_id=rule.pk,
        code=rule.code,
        version=rule.version,
        severity=rule.severity,
        message=rule.message,
        outcome=result.outcome,
        unresolved_fields=result.unresolved_fields,
    )


def evaluate_rules(
    product: BankProduct,
    context: Mapping[str, Any],
    *,
    purpose: CatalogItem | None = None,
    at: datetime | None = None,
) -> list[RuleResult]:
    """Evalúa las reglas aplicables. El paso 8 guardará el resultado en
    ``bank_rule_evaluations`` con la versión exacta de cada regla."""
    return [
        evaluate_rule(rule, context) for rule in applicable_rules(product, purpose=purpose, at=at)
    ]


@dataclass(frozen=True)
class RuleTestCase:
    name: str
    context: dict[str, Any]
    expected: Outcome | None


@dataclass(frozen=True)
class RuleTestResult:
    name: str
    outcome: Outcome
    unresolved_fields: list[str]
    expected: Outcome | None
    matches_expected: bool | None


def run_rule_tests(rule: BankPolicyRule, cases: list[RuleTestCase]) -> list[RuleTestResult]:
    """Ejecuta casos de prueba sobre una versión, sin tocar solicitudes ni la regla."""
    for index, case in enumerate(cases):
        try:
            validate_context(case.context, path=f"cases.{index}.context")
        except ConditionError as exc:
            raise ValidationError({exc.path: [exc.message]}) from exc
    try:
        validate_condition(rule.condition)
    except ConditionError as exc:
        raise RuleConditionInvalid(
            details=[{"field": exc.path, "code": "INVALID_CONDITION", "message": exc.message}]
        ) from exc

    results = []
    for case in cases:
        result = evaluate_condition(rule.condition, case.context)
        results.append(
            RuleTestResult(
                name=case.name,
                outcome=result.outcome,
                unresolved_fields=result.unresolved_fields,
                expected=case.expected,
                matches_expected=None if case.expected is None else result.outcome == case.expected,
            )
        )
    return results
