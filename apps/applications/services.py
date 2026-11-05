"""Casos de uso del módulo applications: alcance, creación, edición y asignación.

Alcance por rol (REQUERIMIENTOS §3 y §8.6, API §25):

- ``ADMIN``: todas las solicitudes.
- ``ADVISOR``: las que tiene asignadas.
- ``INDEPENDENT_BROKER``: solo el resumen de las solicitudes de las oportunidades que
  originó; nunca datos financieros, inmueble ni financiación.
- ``CONSTRUCTION_PARTNER``: ninguna. REQUERIMIENTOS §3 manda sobre API §27.4.

Un recurso fuera del alcance responde 404, para no confirmar que existe.

Todo cambio de los datos del expediente pasa por ``lock_for_edit`` y ``bump_version``:
bloquea la fila, compara la versión de ``If-Match`` y exige un estado previo a `FILED`.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.applications.concurrency import ensure_version
from apps.applications.exceptions import (
    ApplicationAlreadyOpen,
    ApplicationClosed,
    ApplicationNotEditable,
)
from apps.applications.models import (
    FAILED_APPLICATION_STATUSES,
    TERMINAL_APPLICATION_STATUSES,
    ApplicationAssignment,
    ApplicationParticipant,
    ApplicationStatusHistory,
    CreditApplication,
    ParticipantRole,
    Property,
    next_application_code,
)
from apps.applications.signals import (
    application_assigned,
    application_created,
    application_updated,
)
from apps.banking.models import BankProduct
from apps.banking.services import available_products
from apps.catalogs.exceptions import InvalidStateTransition
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus, OpportunityStatus
from apps.crm.models import Client, Opportunity
from apps.crm.services import (
    CrmScope,
    convert_opportunity,
    ensure_advisor,
    get_scope,
    opportunities_visible_to,
)
from apps.identity.models import User
from apps.partners.models import Project
from apps.partners.services import ensure_project_accepts_opportunities, projects_visible_to

logger = logging.getLogger(__name__)

OPEN_APPLICATION_CONSTRAINT = "uq_credit_applications_open_opportunity"

PURCHASE_NEW = "PURCHASE_NEW"
PURCHASE_USED = "PURCHASE_USED"
HOME_IMPROVEMENT = "HOME_IMPROVEMENT"


# --------------------------------------------------------------------------------------
# Alcance
# --------------------------------------------------------------------------------------


def get_application_scope(user: User) -> CrmScope:
    """Mismos roles que CRM: ``is_restricted`` es el broker, que solo ve el resumen."""
    return get_scope(user)


def _scope_filter(user: User, scope: CrmScope) -> Q | None:
    """Filtro de solicitudes visibles, o ``None`` si el usuario ve todas."""
    if scope.sees_everything:
        return None
    condition = Q(pk__in=[])
    if scope.is_advisor:
        condition |= Q(assigned_advisor=user)
    if scope.is_broker:
        condition |= Q(opportunity__origin_user=user)
    return condition


def applications_queryset() -> QuerySet[CreditApplication]:
    return CreditApplication.objects.select_related(
        "opportunity__client__document_type_item",
        "opportunity__origin_item",
        "purpose_item",
        "bank_product__bank",
        "assigned_advisor",
        "withdrawal_reason_item",
        "financed_property__project",
        "financed_property__property_type_item",
        "financed_property__condition_item",
        "financed_property__city_item",
    )


def applications_visible_to(user: User) -> QuerySet[CreditApplication]:
    applications = applications_queryset()
    condition = _scope_filter(user, get_application_scope(user))
    return applications if condition is None else applications.filter(condition)


def client_applications(user: User, client: Client) -> QuerySet[CreditApplication]:
    """Solicitudes visibles en las que el cliente participa (cualquier papel vigente)."""
    return (
        applications_visible_to(user)
        .filter(participants__client=client, participants__is_active=True)
        .distinct()
    )


# --------------------------------------------------------------------------------------
# Referencias recibidas en el cuerpo
# --------------------------------------------------------------------------------------


def resolve_visible_opportunity(user: User, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = opportunities_visible_to(user).filter(pk=opportunity_id).first()
    if opportunity is None:
        raise ValidationError({"opportunity_id": ["La oportunidad no existe."]})
    return opportunity


def resolve_property_project(user: User, project_id: uuid.UUID | None) -> Project | None:
    """El proyecto del inmueble debe ser visible y estar `ACTIVE` (API §18.1)."""
    if project_id is None:
        return None
    project = projects_visible_to(user).filter(pk=project_id).first()
    if project is None:
        raise ValidationError({"project_id": ["El proyecto no existe."]})
    ensure_project_accepts_opportunities(project)
    return project


def resolve_bank_product(product_id: uuid.UUID | None) -> BankProduct | None:
    if product_id is None:
        return None
    product = BankProduct.objects.select_related("bank").filter(pk=product_id).first()
    if product is None:
        raise ValidationError({"bank_product_id": ["El producto no existe."]})
    return product


def _ensure_product_available(product: BankProduct, purpose: CatalogItem, field: str) -> None:
    """El producto debe estar activo, vigente y admitir la finalidad de la solicitud."""
    if not available_products(purpose=purpose).filter(pk=product.pk).exists():
        raise ValidationError(
            {field: ["El producto no está disponible para la finalidad de la solicitud."]}
        )


# --------------------------------------------------------------------------------------
# Inmueble: reglas por finalidad (API §18.1)
# --------------------------------------------------------------------------------------


def property_errors(purpose_code: str, values: Mapping[str, Any]) -> dict[str, list[str]]:
    """Errores del inmueble para la finalidad, por campo (``project_id``, ``address``...).

    - ``PURCHASE_NEW``: es la única que admite proyecto.
    - ``PURCHASE_USED`` y ``HOME_IMPROVEMENT``: exigen dirección.
    - ``HOME_IMPROVEMENT``: exige declarar si el solicitante es propietario.

    Ciudad y valor siempre son obligatorios y los exige el serializer.
    """
    errors: dict[str, list[str]] = {}
    if values.get("project") is not None and purpose_code != PURCHASE_NEW:
        errors["project_id"] = ["Solo la compra de vivienda nueva admite un proyecto."]
    if purpose_code in (PURCHASE_USED, HOME_IMPROVEMENT) and not values.get("address"):
        errors["address"] = ["La dirección es obligatoria para vivienda usada y remodelación."]
    if purpose_code == HOME_IMPROVEMENT and values.get("is_owned_by_applicant") is None:
        errors["is_owned_by_applicant"] = [
            "Declara si el solicitante es propietario del inmueble a remodelar."
        ]
    return errors


def property_values(prop: Property) -> dict[str, Any]:
    return {
        "project": prop.project,
        "address": prop.address,
        "is_owned_by_applicant": prop.is_owned_by_applicant,
    }


def _creation_property_errors(
    purpose: CatalogItem, values: Mapping[str, Any]
) -> dict[str, Any] | None:
    """En ``POST /applications`` el proyecto viaja fuera de ``property`` (API §16.1)."""
    errors = property_errors(purpose.code, values)
    if not errors:
        return None
    nested: dict[str, Any] = {}
    if "project_id" in errors:
        nested["project_id"] = errors.pop("project_id")
    if errors:
        nested["property"] = errors
    return nested


# --------------------------------------------------------------------------------------
# Edición con concurrencia optimista
# --------------------------------------------------------------------------------------


def lock_for_edit(application: CreditApplication, expected_version: int) -> CreditApplication:
    """Bloquea la solicitud para editar su expediente. Llamar dentro de una transacción.

    Comprueba la versión de ``If-Match`` (``409 STALE_VERSION``) y que la solicitud
    esté antes de `FILED` (``409 APPLICATION_NOT_EDITABLE``).
    """
    locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
    ensure_version(locked.version, expected_version)
    if not locked.is_editable:
        raise ApplicationNotEditable()
    return locked


def bump_version(locked: CreditApplication, fields: Iterable[str] = ()) -> None:
    """Guarda los ``fields`` indicados y aumenta la versión del expediente."""
    locked.version += 1
    locked.save(update_fields=[*fields, "version", "updated_at"])


# --------------------------------------------------------------------------------------
# Creación
# --------------------------------------------------------------------------------------


def _already_open_error(actor: User, opportunity: Opportunity) -> ApplicationAlreadyOpen:
    """Error de solicitud en curso. Solo revela su id si el usuario puede verla."""
    open_id = (
        applications_visible_to(actor)
        .filter(opportunity=opportunity)
        .exclude(status__in=TERMINAL_APPLICATION_STATUSES)
        .values_list("pk", flat=True)
        .first()
    )
    details: list[dict[str, Any]] = []
    if open_id:
        details.append(
            {
                "field": "opportunity_id",
                "code": "OPEN_APPLICATION",
                "message": "Continúa la solicitud en curso.",
                "resource_id": str(open_id),
            }
        )
    return ApplicationAlreadyOpen(details=details)


def _ensure_new_attempt_allowed(actor: User, opportunity: Opportunity) -> None:
    """Una oportunidad ya convertida admite otro intento si los anteriores fracasaron."""
    previous = CreditApplication.objects.filter(opportunity=opportunity).exclude(
        status__in=FAILED_APPLICATION_STATUSES
    )
    if previous.exclude(status__in=TERMINAL_APPLICATION_STATUSES).exists():
        raise _already_open_error(actor, opportunity)
    if previous.exists():
        raise InvalidStateTransition("La oportunidad ya tiene una solicitud que terminó con éxito.")


def create_application(
    actor: User,
    *,
    opportunity: Opportunity,
    purpose: CatalogItem,
    advisor: User | None = None,
    property_data: dict[str, Any] | None = None,
) -> CreditApplication:
    """Crea la solicitud `DRAFT` y convierte la oportunidad, todo en una transacción.

    Crea también el titular (el cliente de la oportunidad), el inmueble inicial si
    llega, la asignación inicial y el primer registro del historial de estados. Sin
    ``advisor`` se usa el asesor de la oportunidad.
    """
    advisor = advisor or opportunity.assigned_advisor
    if advisor is None:
        raise ValidationError(
            {"assigned_advisor_id": ["La oportunidad no tiene asesor: indica uno."]}
        )
    ensure_advisor(advisor)
    if property_data is not None:
        errors = _creation_property_errors(purpose, property_data)
        if errors:
            raise ValidationError(errors)

    try:
        with transaction.atomic():
            locked = Opportunity.objects.select_for_update().get(pk=opportunity.pk)
            if locked.status == OpportunityStatus.CONVERTED:
                _ensure_new_attempt_allowed(actor, locked)
            else:
                convert_opportunity(actor, locked)

            application = CreditApplication.objects.create(
                code=next_application_code(),
                opportunity=locked,
                purpose_item=purpose,
                assigned_advisor=advisor,
            )
            ApplicationParticipant.objects.create(
                application=application, client_id=locked.client_id, role=ParticipantRole.PRIMARY
            )
            if property_data is not None:
                Property.objects.create(application=application, **property_data)
            ApplicationAssignment.objects.create(
                application=application, advisor=advisor, assigned_by=actor
            )
            ApplicationStatusHistory.objects.create(
                application=application,
                to_status=ApplicationStatus.DRAFT,
                actor_user=actor,
                application_version=application.version,
            )
    except IntegrityError as exc:
        # Respaldo ante una carrera: la restricción admite una sola solicitud en curso.
        if OPEN_APPLICATION_CONSTRAINT in str(exc):
            raise _already_open_error(actor, opportunity) from exc
        raise

    logger.info("Solicitud %s creada por %s", application.code, actor.pk)
    application_created.send(sender=CreditApplication, application=application, actor=actor)
    return application


# --------------------------------------------------------------------------------------
# Edición de la solicitud (API §16.2)
# --------------------------------------------------------------------------------------


def _changed_fields(application: CreditApplication, changes: Mapping[str, Any]) -> list[str]:
    changed = []
    for field, value in changes.items():
        current = getattr(application, f"{field}_id")
        if current != (value.pk if value is not None else None):
            changed.append(field)
    return changed


def update_application(
    actor: User,
    application: CreditApplication,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> CreditApplication:
    """Cambia la finalidad (``purpose_item``) o el producto (``bank_product``).

    El producto debe admitir la finalidad, y un inmueble ya registrado debe cumplir las
    reglas de la nueva finalidad. Sin cambios reales no aumenta la versión.
    """
    with transaction.atomic():
        locked = lock_for_edit(application, expected_version)
        changed = _changed_fields(locked, changes)
        if not changed:
            return locked

        purpose: CatalogItem = changes.get("purpose_item", locked.purpose_item)
        product: BankProduct | None = (
            changes["bank_product"] if "bank_product" in changed else locked.bank_product
        )
        if product is not None:
            field = "bank_product_id" if "bank_product" in changed else "purpose_code"
            _ensure_product_available(product, purpose, field)
        if "purpose_item" in changed:
            prop = Property.objects.filter(application=locked).select_related("project").first()
            errors = property_errors(purpose.code, property_values(prop)) if prop else {}
            if errors:
                raise ValidationError(
                    {
                        "purpose_code": [
                            "El inmueble registrado no cumple la nueva finalidad "
                            f"({', '.join(sorted(errors))}). Actualízalo primero."
                        ]
                    }
                )

        for field in changed:
            setattr(locked, field, changes[field])
        bump_version(locked, changed)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=sorted(changed), actor=actor
    )
    return locked


# --------------------------------------------------------------------------------------
# Asignación (API §16.1)
# --------------------------------------------------------------------------------------


def assign_application(
    actor: User, application: CreditApplication, *, advisor: User, reason: str = ""
) -> CreditApplication:
    """Reasigna el asesor responsable y conserva el historial.

    Se permite también después de `FILED`; no en una solicitud terminada. No cambia la
    versión del expediente: el responsable no es un dato del crédito.
    """
    ensure_advisor(advisor)
    with transaction.atomic():
        locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
        if locked.is_terminal:
            raise ApplicationClosed()
        previous_advisor_id = locked.assigned_advisor_id
        if previous_advisor_id == advisor.pk:
            return locked

        ApplicationAssignment.objects.filter(application=locked, ended_at__isnull=True).update(
            ended_at=timezone.now()
        )
        ApplicationAssignment.objects.create(
            application=locked, advisor=advisor, assigned_by=actor, reason=reason
        )
        locked.assigned_advisor = advisor
        locked.save(update_fields=["assigned_advisor", "updated_at"])

    application_assigned.send(
        sender=CreditApplication,
        application=locked,
        previous_advisor_id=previous_advisor_id,
        advisor_id=advisor.pk,
        actor=actor,
        reason=reason,
    )
    return locked
