"""Casos de uso del módulo catalogs: catálogos, valores, metadatos y transiciones."""

import uuid
from collections.abc import Iterable
from datetime import date
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogs.exceptions import CatalogNotManageable, DuplicateCode, TransitionNotEditable
from apps.catalogs.models import Catalog, CatalogItem, WorkflowTransition, WorkflowTransitionRole
from apps.catalogs.workflow import guards_for, statuses_for
from apps.identity.models import Permission, Role, RoleCode, User
from apps.identity.services import get_access_profile

SORT_ORDER_STEP = 10


# --------------------------------------------------------------------------------------
# Catálogos y valores
# --------------------------------------------------------------------------------------


def today() -> date:
    """Fecha local de Colombia; las vigencias de los ítems son fechas, no instantes."""
    return timezone.localdate()


def ensure_manageable(catalog: Catalog) -> None:
    if not catalog.is_manageable:
        raise CatalogNotManageable()


def bump_version(catalog_id: uuid.UUID) -> None:
    Catalog.objects.filter(pk=catalog_id).update(
        version=F("version") + 1, updated_at=timezone.now()
    )


def available_items(catalog: Catalog, *, on: date | None = None) -> QuerySet[CatalogItem]:
    """Ítems activos y vigentes en la fecha indicada (por defecto, hoy)."""
    day = on or today()
    return (
        catalog.items.filter(is_active=True)
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=day))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .select_related("parent_item")
        .order_by("sort_order", "label")
    )


def create_catalog(*, code: str, name: str, description: str, is_public: bool) -> Catalog:
    try:
        with transaction.atomic():
            return Catalog.objects.create(
                code=code, name=name, description=description, is_public=is_public
            )
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe un catálogo con ese código.") from exc


def update_catalog(catalog: Catalog, changes: dict[str, Any]) -> Catalog:
    ensure_manageable(catalog)
    if not changes:
        return catalog
    for field, value in changes.items():
        setattr(catalog, field, value)
    catalog.version = F("version") + 1
    catalog.save(update_fields=[*changes, "version", "updated_at"])
    catalog.refresh_from_db()
    return catalog


def _validate_validity(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from and valid_to and valid_to < valid_from:
        raise ValidationError(
            {"valid_to": ["La fecha final de vigencia no puede ser anterior a la inicial."]}
        )


def create_item(catalog: Catalog, data: dict[str, Any]) -> CatalogItem:
    ensure_manageable(catalog)
    _validate_validity(data.get("valid_from"), data.get("valid_to"))

    with transaction.atomic():
        locked = Catalog.objects.select_for_update().get(pk=catalog.pk)
        if data.get("sort_order") is None:
            current_max = locked.items.aggregate(value=Max("sort_order"))["value"]
            data["sort_order"] = (current_max or 0) + SORT_ORDER_STEP
        try:
            with transaction.atomic():
                item = CatalogItem.objects.create(catalog=locked, **data)
        except IntegrityError as exc:
            raise DuplicateCode("Ya existe un valor con ese código en el catálogo.") from exc
        bump_version(locked.pk)
    return item


def update_item(item: CatalogItem, changes: dict[str, Any]) -> CatalogItem:
    ensure_manageable(item.catalog)
    _validate_validity(
        changes.get("valid_from", item.valid_from), changes.get("valid_to", item.valid_to)
    )
    if not changes:
        return item
    with transaction.atomic():
        for field, value in changes.items():
            setattr(item, field, value)
        item.save(update_fields=[*changes, "updated_at"])
        bump_version(item.catalog_id)
    return item


def set_item_active(item: CatalogItem, *, active: bool) -> CatalogItem:
    """Activa o desactiva un valor. Desactivar no afecta los registros históricos."""
    ensure_manageable(item.catalog)
    if item.is_active == active:
        return item
    with transaction.atomic():
        item.is_active = active
        item.save(update_fields=["is_active", "updated_at"])
        bump_version(item.catalog_id)
    return item


def reorder_items(catalog: Catalog, item_ids: list[uuid.UUID]) -> QuerySet[CatalogItem]:
    """Asigna el orden recibido. La lista debe incluir todos los ítems del catálogo."""
    ensure_manageable(catalog)
    with transaction.atomic():
        locked = Catalog.objects.select_for_update().get(pk=catalog.pk)
        items = {item.pk: item for item in locked.items.all()}

        missing = set(items) - set(item_ids)
        unknown = set(item_ids) - set(items)
        if missing or unknown:
            raise ValidationError(
                {
                    "item_ids": [
                        "Debe incluir exactamente todos los valores del catálogo, una vez cada uno."
                    ]
                }
            )

        for index, item_id in enumerate(item_ids):
            items[item_id].sort_order = (index + 1) * SORT_ORDER_STEP
        CatalogItem.objects.bulk_update(items.values(), ["sort_order"])
        CatalogItem.objects.filter(catalog=locked).update(updated_at=timezone.now())
        bump_version(locked.pk)
    return locked.items.select_related("parent_item").order_by("sort_order", "label")


# --------------------------------------------------------------------------------------
# Metadatos para el frontend
# --------------------------------------------------------------------------------------


def serialize_metadata_item(item: CatalogItem) -> dict[str, Any]:
    return {
        "id": str(item.pk),
        "code": item.code,
        "label": item.label,
        "description": item.description,
        "order": item.sort_order,
        "active": item.is_active,
        "parent_id": str(item.parent_item_id) if item.parent_item_id else None,
        "parent_code": item.parent_item.code if item.parent_item else None,
        "metadata": item.metadata,
    }


def catalog_metadata(
    catalog: Catalog, *, parent_id: uuid.UUID | None = None, parent_code: str | None = None
) -> dict[str, Any]:
    items = available_items(catalog)
    if parent_id is not None:
        items = items.filter(parent_item_id=parent_id)
    if parent_code is not None:
        items = items.filter(parent_item__code=parent_code)
    return {
        "catalog": catalog.code,
        "name": catalog.name,
        "version": catalog.version,
        "items": [serialize_metadata_item(item) for item in items],
    }


def bootstrap_catalogs() -> QuerySet[Catalog]:
    """Catálogos que viajan en el bootstrap; los grandes se piden bajo demanda.

    Por ahora solo hay usuarios internos, que ven todos los catálogos. Cuando exista
    la sesión del comprador (paso 9), el comprador solo recibirá los `is_public`.
    """
    return Catalog.objects.exclude(code__in=settings.METADATA_ON_DEMAND_CATALOGS).order_by("code")


def bootstrap(user: User) -> dict[str, Any]:
    profile = get_access_profile(user)
    catalogs = list(bootstrap_catalogs())
    day = today()
    return {
        # Suma de versiones: crece con cualquier cambio de los catálogos incluidos.
        "metadata_version": sum(catalog.version for catalog in catalogs),
        "actor": profile.role,
        "permissions": profile.permissions,
        "catalogs": {
            catalog.code: [
                serialize_metadata_item(item) for item in available_items(catalog, on=day)
            ]
            for catalog in catalogs
        },
        "on_demand_catalogs": sorted(settings.METADATA_ON_DEMAND_CATALOGS),
        "features": dict(settings.PUBLIC_FEATURES),
    }


# --------------------------------------------------------------------------------------
# Transiciones de estado
# --------------------------------------------------------------------------------------


def _validate_transition(
    *, flow_type: str, from_status: str, to_status: str, guard_code: str
) -> None:
    errors: dict[str, list[str]] = {}
    allowed = statuses_for(flow_type)
    if from_status not in allowed:
        errors["from_status"] = [f"Estado no válido para el flujo {flow_type}."]
    if to_status not in allowed:
        errors["to_status"] = [f"Estado no válido para el flujo {flow_type}."]
    if from_status == to_status:
        errors.setdefault("to_status", []).append("El estado destino debe ser distinto al origen.")
    if guard_code and guard_code not in guards_for(flow_type):
        errors["guard_code"] = [f"Guarda no implementada para el flujo {flow_type}."]
    if errors:
        raise ValidationError(errors)


def _resolve_permission(code: str | None) -> Permission | None:
    if not code:
        return None
    permission = Permission.objects.filter(code=code).first()
    if permission is None:
        raise ValidationError({"required_permission": ["El permiso no existe."]})
    return permission


def _resolve_roles(codes: Iterable[str]) -> list[Role]:
    codes = list(dict.fromkeys(codes))
    roles = list(Role.objects.filter(code__in=codes))
    unknown = sorted(set(codes) - {role.code for role in roles})
    if unknown:
        raise ValidationError({"roles": [f"Roles inexistentes: {', '.join(unknown)}."]})
    return roles


def _set_roles(transition: WorkflowTransition, roles: list[Role]) -> None:
    WorkflowTransitionRole.objects.filter(transition=transition).exclude(role__in=roles).delete()
    existing = set(
        WorkflowTransitionRole.objects.filter(transition=transition).values_list(
            "role_id", flat=True
        )
    )
    WorkflowTransitionRole.objects.bulk_create(
        [
            WorkflowTransitionRole(transition=transition, role=role)
            for role in roles
            if role.pk not in existing
        ]
    )


def create_transition(data: dict[str, Any]) -> WorkflowTransition:
    """Crea una transición siempre inactiva (sección 23.5)."""
    guard_code = data.get("guard_code") or ""
    _validate_transition(
        flow_type=data["flow_type"],
        from_status=data["from_status"],
        to_status=data["to_status"],
        guard_code=guard_code,
    )
    permission = _resolve_permission(data.get("required_permission"))
    roles = _resolve_roles(data["roles"])
    try:
        with transaction.atomic():
            transition = WorkflowTransition.objects.create(
                flow_type=data["flow_type"],
                code=data["code"],
                from_status=data["from_status"],
                to_status=data["to_status"],
                label=data["label"],
                required_permission=permission,
                guard_code=guard_code,
                is_active=False,
            )
            _set_roles(transition, roles)
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe una transición con ese código en el flujo.") from exc
    return transition


def update_transition(
    transition: WorkflowTransition, changes: dict[str, Any]
) -> WorkflowTransition:
    if transition.is_active:
        raise TransitionNotEditable()

    guard_code = changes.get("guard_code", transition.guard_code) or ""
    _validate_transition(
        flow_type=transition.flow_type,
        from_status=changes.get("from_status", transition.from_status),
        to_status=changes.get("to_status", transition.to_status),
        guard_code=guard_code,
    )

    with transaction.atomic():
        update_fields = ["updated_at"]
        for field in ("label", "from_status", "to_status"):
            if field in changes:
                setattr(transition, field, changes[field])
                update_fields.append(field)
        if "guard_code" in changes:
            transition.guard_code = guard_code
            update_fields.append("guard_code")
        if "required_permission" in changes:
            transition.required_permission = _resolve_permission(changes["required_permission"])
            update_fields.append("required_permission")
        transition.save(update_fields=update_fields)
        if "roles" in changes:
            _set_roles(transition, _resolve_roles(changes["roles"]))
    return transition


def set_transition_active(transition: WorkflowTransition, *, active: bool) -> WorkflowTransition:
    if transition.is_active != active:
        transition.is_active = active
        transition.save(update_fields=["is_active", "updated_at"])
    return transition


def available_transitions(
    user: User, *, flow_type: str, from_status: str
) -> QuerySet[WorkflowTransition]:
    """Transiciones activas que ``user`` puede ejecutar desde ``from_status``.

    Exige que el usuario tenga uno de los roles de la transición (`ADMIN` no
    necesita figurar en la lista) y, si existe, el permiso requerido. Una transición
    sin roles solo está disponible para `ADMIN`. Las guardas no se evalúan aquí: las
    evalúa el módulo dueño del flujo.
    """
    transitions = WorkflowTransition.objects.filter(
        flow_type=flow_type, from_status=from_status, is_active=True
    ).select_related("required_permission")

    if user.is_superuser:
        return transitions.order_by("code")

    profile = get_access_profile(user)
    if RoleCode.ADMIN not in profile.roles:
        transitions = transitions.filter(roles__code__in=profile.roles)
    return (
        transitions.filter(
            Q(required_permission__isnull=True)
            | Q(required_permission__code__in=profile.permissions)
        )
        .distinct()
        .order_by("code")
    )
