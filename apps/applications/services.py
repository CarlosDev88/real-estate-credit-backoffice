"""Casos de uso de applications: alcance, creación, edición, asignación, participantes,
inmueble y financiación.

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
from django.db.models import Prefetch, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.applications.concurrency import ensure_version
from apps.applications.exceptions import (
    ApplicationAlreadyOpen,
    ApplicationClosed,
    ApplicationNotEditable,
    ParticipantInactive,
)
from apps.applications.models import (
    FAILED_APPLICATION_STATUSES,
    TERMINAL_APPLICATION_STATUSES,
    ApplicationAssignment,
    ApplicationParticipant,
    ApplicationStatusHistory,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    ParticipantRole,
    Property,
    next_application_code,
)
from apps.applications.signals import (
    application_assigned,
    application_created,
    application_updated,
    participant_added,
    participant_removed,
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
    create_client,
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

# Modalidades de financiación (catálogo `financing_mode`).
BANK_CREDIT = "BANK_CREDIT"
OWN_FUNDS = "OWN_FUNDS"
EXTERNAL_CREDIT = "EXTERNAL_CREDIT"


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


def application_detail(
    user: User, application_id: uuid.UUID, include: Iterable[str] = ()
) -> CreditApplication | None:
    """Solicitud visible con los bloques de ``?include=`` precargados."""
    blocks = set(include)
    applications = applications_visible_to(user)
    if "participants" in blocks:
        applications = applications.prefetch_related(
            Prefetch(
                "participants",
                queryset=participants_queryset().filter(is_active=True),
                to_attr="active_participants",
            )
        )
    if "financing" in blocks:
        applications = applications.select_related(
            "financing__financing_mode_item",
            "financing__currency_mode_item",
            "financing__amortization_mode_item",
        )
    return applications.filter(pk=application_id).first()


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


def lock_for_edit(
    application: CreditApplication | uuid.UUID, expected_version: int | None
) -> CreditApplication:
    """Bloquea la solicitud para editar su expediente. Llamar dentro de una transacción.

    Comprueba la versión de ``If-Match`` (``409 STALE_VERSION``) y que la solicitud
    esté antes de `FILED` (``409 APPLICATION_NOT_EDITABLE``). Con ``expected_version``
    en ``None`` no compara la versión: es el caso de los ``POST`` que crean subrecursos
    y de los ``DELETE`` (API §6).
    """
    pk = application.pk if isinstance(application, CreditApplication) else application
    locked = CreditApplication.objects.select_for_update().get(pk=pk)
    if expected_version is not None:
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


def _ensure_product_fits_financing(
    application: CreditApplication, product: BankProduct | None
) -> None:
    """El producto del ``PATCH`` debe cuadrar con la modalidad de financiación registrada.

    Sin financiación registrada no hay nada que comparar.
    """
    mode = (
        FinancingPreference.objects.filter(application=application)
        .values_list("financing_mode_item__code", flat=True)
        .first()
    )
    if mode is None:
        return
    if mode != BANK_CREDIT and product is not None:
        raise ValidationError(
            {
                "bank_product_id": [
                    "La financiación registrada no es crédito bancario: cambia la "
                    "modalidad en `/financing`."
                ]
            }
        )
    if mode == BANK_CREDIT and product is None:
        raise ValidationError(
            {
                "bank_product_id": [
                    "El crédito bancario necesita un producto: para quitarlo, cambia la "
                    "modalidad en `/financing`."
                ]
            }
        )


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
        if "bank_product" in changed:
            _ensure_product_fits_financing(locked, product)
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


# --------------------------------------------------------------------------------------
# Participantes, perfil financiero e ingresos (API §17)
# --------------------------------------------------------------------------------------
#
# Todo cambio bloquea la solicitud con ``lock_for_edit`` (estado previo a `FILED`) y
# aumenta su versión. Los ``PATCH``/``PUT`` comparan la versión de ``If-Match``; los
# ``POST`` y ``DELETE`` no. Los subrecursos se vuelven a leer después del bloqueo, para
# no decidir con datos que otra petición acaba de cambiar.

ADDITIONAL_PARTICIPANT_ROLES = (ParticipantRole.CO_APPLICANT, ParticipantRole.SOLIDARY_DEBTOR)


def participants_queryset() -> QuerySet[ApplicationParticipant]:
    return ApplicationParticipant.objects.select_related(
        "client__document_type_item",
        "client__origin_item",
        "client__created_by",
        "financial_profile",
    )


def participants_visible_to(user: User) -> QuerySet[ApplicationParticipant]:
    """Participantes de las solicitudes visibles; el resto responde 404."""
    return participants_queryset().filter(application__in=applications_visible_to(user))


def financial_profiles_visible_to(user: User) -> QuerySet[FinancialProfile]:
    return (
        FinancialProfile.objects.select_related(
            "participant",
            "employment_profile_item",
            "contract_type_item",
            "funds_origin_item",
        )
        .annotate(income_sources_total_cop=Coalesce(Sum("income_sources__monthly_amount_cop"), 0))
        .filter(participant__application__in=applications_visible_to(user))
    )


def income_sources_visible_to(user: User) -> QuerySet[IncomeSource]:
    return IncomeSource.objects.select_related(
        "financial_profile__participant", "source_type_item"
    ).filter(financial_profile__participant__application__in=applications_visible_to(user))


def _current_participant(
    participant_id: uuid.UUID, *, active: bool = True
) -> ApplicationParticipant:
    """Relee el participante con la solicitud bloqueada y exige que siga vigente."""
    participant = ApplicationParticipant.objects.get(pk=participant_id)
    if active and not participant.is_active:
        raise ParticipantInactive()
    return participant


def _ensure_income_share(contributes_income: bool, income_share_cop: int | None) -> None:
    if not contributes_income and income_share_cop is not None:
        raise ValidationError(
            {"income_share_cop": ["Solo se declara aporte si el participante aporta ingresos."]}
        )


def _changed(instance: Any, changes: Mapping[str, Any]) -> list[str]:
    return [field for field, value in changes.items() if getattr(instance, field) != value]


def add_participant(
    actor: User,
    application: CreditApplication,
    *,
    role: str,
    client: Client | None = None,
    client_data: dict[str, Any] | None = None,
    contributes_income: bool = True,
    income_share_cop: int | None = None,
) -> ApplicationParticipant:
    """Agrega un co-solicitante o deudor solidario.

    Recibe un cliente visible (``client``) o sus datos de identidad (``client_data``),
    con los que crea el cliente en la misma transacción (``409
    DUPLICATE_CLIENT_DOCUMENT`` si el documento ya existe). Un cliente retirado de la
    solicitud se reactiva en su misma fila, porque ``(application, client)`` es única.
    """
    if role not in ADDITIONAL_PARTICIPANT_ROLES:
        raise ValidationError({"role_code": ["El titular se crea con la solicitud."]})
    _ensure_income_share(contributes_income, income_share_cop)
    values = {
        "role": role,
        "contributes_income": contributes_income,
        "income_share_cop": income_share_cop,
    }

    with transaction.atomic():
        locked = lock_for_edit(application, None)
        if client is None:
            if client_data is None:
                raise ValueError("Se necesita client o client_data.")
            client = create_client(actor, client_data)
        participant = ApplicationParticipant.objects.filter(
            application=locked, client=client
        ).first()
        reactivated = participant is not None
        if participant is None:
            participant = ApplicationParticipant.objects.create(
                application=locked, client=client, **values
            )
        elif participant.is_active:
            raise ValidationError({"client_id": ["El cliente ya participa en la solicitud."]})
        else:
            for field, value in values.items():
                setattr(participant, field, value)
            participant.is_active = True
            participant.save(update_fields=[*values, "is_active", "updated_at"])
        bump_version(locked)

    logger.info("Participante %s agregado a %s por %s", participant.pk, locked.code, actor.pk)
    participant_added.send(
        sender=CreditApplication,
        application=locked,
        participant=participant,
        reactivated=reactivated,
        actor=actor,
    )
    return participant


def update_participant(
    actor: User,
    participant: ApplicationParticipant,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> ApplicationParticipant:
    """Cambia el papel adicional, si aporta ingresos o su aporte declarado.

    El titular conserva su papel. Sin cambios reales no aumenta la versión.
    """
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, expected_version)
        current = _current_participant(participant.pk)
        changed = _changed(current, changes)
        if not changed:
            return current
        if "role" in changed:
            if current.role == ParticipantRole.PRIMARY:
                raise ValidationError({"role_code": ["El titular no cambia de papel."]})
            if changes["role"] not in ADDITIONAL_PARTICIPANT_ROLES:
                raise ValidationError({"role_code": ["La solicitud ya tiene un titular."]})
        for field in changed:
            setattr(current, field, changes[field])
        _ensure_income_share(current.contributes_income, current.income_share_cop)
        current.save(update_fields=[*changed, "updated_at"])
        bump_version(locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=["participants"], actor=actor
    )
    return current


def remove_participant(actor: User, participant: ApplicationParticipant) -> None:
    """Retira un participante adicional (``is_active = false``). Repetirlo no hace nada."""
    if participant.role == ParticipantRole.PRIMARY:
        raise ValidationError({"role": ["El titular no se retira de la solicitud."]})
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, None)
        current = _current_participant(participant.pk, active=False)
        if not current.is_active:
            return
        current.is_active = False
        current.save(update_fields=["is_active", "updated_at"])
        bump_version(locked)

    logger.info("Participante %s retirado de %s por %s", current.pk, locked.code, actor.pk)
    participant_removed.send(
        sender=CreditApplication, application=locked, participant=current, actor=actor
    )


def put_financial_profile(
    actor: User,
    participant: ApplicationParticipant,
    *,
    expected_version: int,
    values: dict[str, Any],
) -> bool:
    """Crea o reemplaza el perfil financiero. Devuelve ``True`` si lo creó.

    ``values`` trae todos los campos editables: lo que el cliente no envió llega con su
    valor por omisión. ``data_confirmed_at`` no se toca: lo confirma el comprador
    (paso 9). Reemplazar con los mismos datos no aumenta la versión.
    """
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, expected_version)
        current = _current_participant(participant.pk)
        profile = FinancialProfile.objects.filter(participant=current).first()
        created = profile is None
        if profile is None:
            FinancialProfile.objects.create(participant=current, **values)
        else:
            changed = _changed(profile, values)
            if not changed:
                return False
            for field in changed:
                setattr(profile, field, values[field])
            profile.save(update_fields=[*changed, "updated_at"])
        bump_version(locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=["financial_profile"], actor=actor
    )
    return created


def _unmark_other_primary_sources(profile_id: uuid.UUID, keep: uuid.UUID | None) -> None:
    """Un perfil tiene como máximo una fuente principal: la nueva desplaza a la anterior."""
    sources = IncomeSource.objects.filter(financial_profile_id=profile_id, is_primary=True)
    if keep is not None:
        sources = sources.exclude(pk=keep)
    sources.update(is_primary=False, updated_at=timezone.now())


def _income_sources_changed(locked: CreditApplication, actor: User) -> None:
    application_updated.send(
        sender=CreditApplication, application=locked, fields=["income_sources"], actor=actor
    )


def add_income_source(
    actor: User, profile: FinancialProfile, values: dict[str, Any]
) -> IncomeSource:
    with transaction.atomic():
        locked = lock_for_edit(profile.participant.application_id, None)
        _current_participant(profile.participant_id)
        if values.get("is_primary"):
            _unmark_other_primary_sources(profile.pk, keep=None)
        source = IncomeSource.objects.create(financial_profile=profile, **values)
        bump_version(locked)

    _income_sources_changed(locked, actor)
    return source


def update_income_source(
    actor: User,
    source: IncomeSource,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> IncomeSource:
    """Edita una fuente. Sin cambios reales no aumenta la versión."""
    participant = source.financial_profile.participant
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, expected_version)
        _current_participant(participant.pk)
        current = IncomeSource.objects.get(pk=source.pk)
        changed = _changed(current, changes)
        if not changed:
            return current
        if changes.get("is_primary"):
            _unmark_other_primary_sources(current.financial_profile_id, keep=current.pk)
        for field in changed:
            setattr(current, field, changes[field])
        current.save(update_fields=[*changed, "updated_at"])
        bump_version(locked)

    _income_sources_changed(locked, actor)
    return current


def delete_income_source(actor: User, source: IncomeSource) -> None:
    participant = source.financial_profile.participant
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, None)
        _current_participant(participant.pk)
        IncomeSource.objects.filter(pk=source.pk).delete()
        bump_version(locked)

    _income_sources_changed(locked, actor)


# --------------------------------------------------------------------------------------
# Inmueble y financiación (API §18.1 y §18.2)
# --------------------------------------------------------------------------------------
#
# Los dos ``PUT`` reemplazan el subrecurso completo, exigen ``If-Match`` y responden si
# lo crearon. Reemplazar con los mismos datos no aumenta la versión.


def put_property(
    actor: User,
    application: CreditApplication,
    *,
    expected_version: int,
    values: dict[str, Any],
) -> bool:
    """Crea o reemplaza el inmueble. Devuelve ``True`` si lo creó.

    ``values`` trae los campos del modelo, con ``project`` ya resuelto (visible y
    `ACTIVE`). Las reglas por finalidad se comprueban con la solicitud bloqueada, para
    no decidir con una finalidad que otra petición acaba de cambiar.
    """
    with transaction.atomic():
        locked = lock_for_edit(application, expected_version)
        errors = property_errors(locked.purpose_item.code, values)
        if errors:
            raise ValidationError(errors)
        prop = Property.objects.filter(application=locked).first()
        created = prop is None
        if prop is None:
            Property.objects.create(application=locked, **values)
        else:
            changed = _changed(prop, values)
            if not changed:
                return False
            for field in changed:
                setattr(prop, field, values[field])
            prop.save(update_fields=[*changed, "updated_at"])
        bump_version(locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=["property"], actor=actor
    )
    return created


def financing_errors(
    mode_code: str, values: Mapping[str, Any], product: BankProduct | None
) -> dict[str, list[str]]:
    """Errores que cruzan la modalidad con el producto y los montos, por campo.

    - ``BANK_CREDIT``: exige producto y monto solicitado; no lleva monto externo.
    - ``OWN_FUNDS`` y ``EXTERNAL_CREDIT``: sin producto y con monto solicitado en 0.
    - ``EXTERNAL_CREDIT``: exige el monto aprobado por otra entidad; los demás modos no
      lo aceptan.
    - Sin cesantías, su monto es 0 (CHECK ``ck_financing_severance``).

    Los rangos de monto y plazo del producto no se validan al guardar: los verifica la
    evaluación bancaria como validación bloqueante del sistema (Parte 5).
    """
    errors: dict[str, list[str]] = {}
    if mode_code == BANK_CREDIT:
        if product is None:
            errors["bank_product_id"] = ["El crédito bancario necesita un producto."]
        if values.get("requested_amount_cop") is None:
            errors["requested_amount_cop"] = ["Indica el monto solicitado al banco."]
    else:
        if product is not None:
            errors["bank_product_id"] = ["Solo el crédito bancario lleva producto."]
        if values.get("requested_amount_cop") not in (None, 0):
            errors["requested_amount_cop"] = [
                "Sin crédito bancario no se solicita monto: déjalo vacío o en 0."
            ]
    external = values.get("external_approved_amount_cop")
    if mode_code == EXTERNAL_CREDIT and external is None:
        errors["external_approved_amount_cop"] = ["Indica el monto aprobado por la otra entidad."]
    if mode_code != EXTERNAL_CREDIT and external is not None:
        errors["external_approved_amount_cop"] = [
            "Solo el crédito externo lleva monto aprobado por otra entidad."
        ]
    if not values.get("uses_severance_funds") and values.get("severance_funds_cop"):
        errors["severance_funds_cop"] = ["Sin uso de cesantías, el monto de cesantías es 0."]
    return errors


def put_financing(
    actor: User,
    application: CreditApplication,
    *,
    expected_version: int,
    values: dict[str, Any],
    product: BankProduct | None,
) -> bool:
    """Crea o reemplaza la financiación y el producto elegido. Devuelve ``True`` si la creó.

    El producto se guarda en ``credit_applications.bank_product``; con ``OWN_FUNDS`` o
    ``EXTERNAL_CREDIT`` se limpia. Con crédito bancario debe estar disponible para la
    finalidad de la solicitud.
    """
    errors = financing_errors(values["financing_mode_item"].code, values, product)
    if errors:
        raise ValidationError(errors)
    values = {**values, "requested_amount_cop": values["requested_amount_cop"] or 0}

    with transaction.atomic():
        locked = lock_for_edit(application, expected_version)
        financing = FinancingPreference.objects.filter(application=locked).first()
        created = financing is None
        changed = list(values) if financing is None else _changed(financing, values)
        product_changed = locked.bank_product_id != (product.pk if product else None)
        if not changed and not product_changed:
            return False
        if product is not None:
            _ensure_product_available(product, locked.purpose_item, "bank_product_id")

        if financing is None:
            FinancingPreference.objects.create(application=locked, **values)
        elif changed:
            for field in changed:
                setattr(financing, field, values[field])
            financing.save(update_fields=[*changed, "updated_at"])
        fields = ["financing"] if changed else []
        if product_changed:
            locked.bank_product = product
            fields.append("bank_product")
        bump_version(locked, ["bank_product"] if product_changed else [])

    application_updated.send(
        sender=CreditApplication, application=locked, fields=sorted(fields), actor=actor
    )
    return created
