"""Casos de uso de applications: alcance, creación, edición, asignación, participantes,
inmueble, financiación, evaluación de reglas bancarias, estados y completitud.

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
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.applications.bank_evaluation import (
    EvaluationSummary,
    blocking_rows,
    evaluate_product,
    is_current,
    issue,
    save_evaluation,
    summarize,
)
from apps.applications.concurrency import ensure_version
from apps.applications.exceptions import (
    ApplicationAlreadyOpen,
    ApplicationClosed,
    ApplicationNotEditable,
    ApplicationNotReady,
    BankProductRequired,
    FinancingModeMismatch,
    ParticipantInactive,
)
from apps.applications.models import (
    EDITABLE_APPLICATION_STATUSES,
    FAILED_APPLICATION_STATUSES,
    TERMINAL_APPLICATION_STATUSES,
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
    next_application_code,
)
from apps.applications.rule_context import build_rule_context
from apps.applications.signals import (
    application_assigned,
    application_created,
    application_status_changed,
    application_updated,
    participant_added,
    participant_removed,
)
from apps.banking.models import BankProduct
from apps.banking.services import available_products
from apps.catalogs.exceptions import InvalidStateTransition
from apps.catalogs.models import CatalogItem, WorkflowTransition
from apps.catalogs.services import available_transitions, resolve_transition
from apps.catalogs.workflow import ApplicationStatus, FlowType, OpportunityStatus
from apps.crm.models import Client, Opportunity
from apps.crm.services import (
    CrmScope,
    convert_opportunity,
    create_client,
    ensure_advisor,
    get_scope,
    opportunities_visible_to,
)
from apps.identity.models import BuyerSession, User
from apps.partners.models import Project
from apps.partners.services import ensure_project_accepts_opportunities, projects_visible_to

logger = logging.getLogger(__name__)

# Quién hace un cambio del expediente: un usuario interno o la sesión del comprador
# (paso 9). Los servicios que usa el portal del comprador aceptan los dos.
Actor = User | BuyerSession

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
    reglas de la nueva finalidad. Sin cambios reales no aumenta la versión. Elegir un
    producto guarda una evaluación de sus reglas con la versión nueva.
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
        if "bank_product" in changed and product is not None:
            save_evaluation(actor, locked)

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


def financial_profiles_queryset() -> QuerySet[FinancialProfile]:
    return FinancialProfile.objects.select_related(
        "participant",
        "employment_profile_item",
        "contract_type_item",
        "funds_origin_item",
    ).annotate(income_sources_total_cop=Coalesce(Sum("income_sources__monthly_amount_cop"), 0))


def financial_profiles_visible_to(user: User) -> QuerySet[FinancialProfile]:
    return financial_profiles_queryset().filter(
        participant__application__in=applications_visible_to(user)
    )


def income_sources_queryset() -> QuerySet[IncomeSource]:
    return IncomeSource.objects.select_related("financial_profile__participant", "source_type_item")


def income_sources_visible_to(user: User) -> QuerySet[IncomeSource]:
    return income_sources_queryset().filter(
        financial_profile__participant__application__in=applications_visible_to(user)
    )


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


def _clear_data_confirmation(profile_id: uuid.UUID) -> None:
    """Un cambio real del perfil o de sus ingresos invalida la confirmación del comprador."""
    FinancialProfile.objects.filter(pk=profile_id, data_confirmed_at__isnull=False).update(
        data_confirmed_at=None, updated_at=timezone.now()
    )


def put_financial_profile(
    actor: Actor,
    participant: ApplicationParticipant,
    *,
    expected_version: int,
    values: dict[str, Any],
) -> bool:
    """Crea o reemplaza el perfil financiero. Devuelve ``True`` si lo creó.

    ``values`` trae todos los campos editables: lo que el cliente no envió llega con su
    valor por omisión. ``values`` nunca trae ``data_confirmed_at``: lo fija la
    confirmación del comprador, y un cambio real lo limpia. Reemplazar con los mismos
    datos no aumenta la versión.
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
            profile.data_confirmed_at = None
            profile.save(update_fields=[*changed, "data_confirmed_at", "updated_at"])
        bump_version(locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=["financial_profile"], actor=actor
    )
    return created


def confirm_financial_profile(
    actor: Actor, participant: ApplicationParticipant, *, expected_version: int
) -> FinancialProfile:
    """El comprador confirma el perfil (``data_confirmed_at = now``) y aumenta la versión.

    Sin perfil responde ``404``. Confirmar un perfil ya confirmado no cambia nada.
    """
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, expected_version)
        current = _current_participant(participant.pk)
        profile = FinancialProfile.objects.select_for_update().filter(participant=current).first()
        if profile is None:
            raise NotFound("El participante todavía no tiene perfil financiero.")
        if profile.data_confirmed_at is not None:
            return profile
        profile.data_confirmed_at = timezone.now()
        profile.save(update_fields=["data_confirmed_at", "updated_at"])
        bump_version(locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=["financial_profile"], actor=actor
    )
    return profile


def _unmark_other_primary_sources(profile_id: uuid.UUID, keep: uuid.UUID | None) -> None:
    """Un perfil tiene como máximo una fuente principal: la nueva desplaza a la anterior."""
    sources = IncomeSource.objects.filter(financial_profile_id=profile_id, is_primary=True)
    if keep is not None:
        sources = sources.exclude(pk=keep)
    sources.update(is_primary=False, updated_at=timezone.now())


def _income_sources_changed(locked: CreditApplication, actor: Actor) -> None:
    application_updated.send(
        sender=CreditApplication, application=locked, fields=["income_sources"], actor=actor
    )


def add_income_source(
    actor: Actor, profile: FinancialProfile, values: dict[str, Any]
) -> IncomeSource:
    with transaction.atomic():
        locked = lock_for_edit(profile.participant.application_id, None)
        _current_participant(profile.participant_id)
        if values.get("is_primary"):
            _unmark_other_primary_sources(profile.pk, keep=None)
        source = IncomeSource.objects.create(financial_profile=profile, **values)
        _clear_data_confirmation(profile.pk)
        bump_version(locked)

    _income_sources_changed(locked, actor)
    return source


def update_income_source(
    actor: Actor,
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
        _clear_data_confirmation(current.financial_profile_id)
        bump_version(locked)

    _income_sources_changed(locked, actor)
    return current


def delete_income_source(actor: Actor, source: IncomeSource) -> None:
    participant = source.financial_profile.participant
    with transaction.atomic():
        locked = lock_for_edit(participant.application_id, None)
        _current_participant(participant.pk)
        IncomeSource.objects.filter(pk=source.pk).delete()
        _clear_data_confirmation(source.financial_profile_id)
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
    finalidad de la solicitud. Elegir un producto distinto guarda una evaluación de sus
    reglas con la versión nueva.
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
        if product_changed and product is not None:
            save_evaluation(actor, locked)

    application_updated.send(
        sender=CreditApplication, application=locked, fields=sorted(fields), actor=actor
    )
    return created


# --------------------------------------------------------------------------------------
# Reglas bancarias (API §18.2)
# --------------------------------------------------------------------------------------


def evaluate_application(actor: User, application: CreditApplication) -> BankRuleEvaluation:
    """Evalúa las reglas del producto elegido y guarda el resultado.

    Solo antes de `FILED` (``409 APPLICATION_NOT_EDITABLE``) y con producto
    (``422 BANK_PRODUCT_REQUIRED``). No cambia la versión; bloquea la solicitud para que
    el contexto evaluado corresponda exactamente a ``application_version``.
    """
    with transaction.atomic():
        locked = lock_for_edit(application, None)
        if locked.bank_product_id is None:
            raise BankProductRequired()
        evaluation = save_evaluation(actor, locked)
    logger.info(
        "Reglas de %s evaluadas por %s: elegible=%s",
        locked.code,
        actor.pk,
        evaluation.is_eligible,
    )
    return evaluation


def latest_evaluation(application: CreditApplication) -> BankRuleEvaluation | None:
    return (
        BankRuleEvaluation.objects.filter(application=application).order_by("-created_at").first()
    )


def eligible_products_queryset(application: CreditApplication) -> QuerySet[BankProduct]:
    """Productos disponibles hoy para la finalidad, por banco y producto."""
    return available_products(purpose=application.purpose_item).order_by("bank__name", "name", "id")


def preview_products(
    application: CreditApplication, products: Iterable[BankProduct]
) -> dict[uuid.UUID, EvaluationSummary]:
    """Evaluación no persistida de cada producto, con el contexto actual de la solicitud."""
    context = build_rule_context(application)
    return {
        product.pk: summarize(evaluate_product(product, context, purpose=application.purpose_item))
        for product in products
    }


# --------------------------------------------------------------------------------------
# Estados (API §16.3), desistimiento y acciones disponibles
# --------------------------------------------------------------------------------------

READY_TO_FILE_GUARD = "APPLICATION_READY_TO_FILE"
# Cierres que exigen `reason_code`.
REASON_REQUIRED_STATUSES: tuple[str, ...] = (
    ApplicationStatus.CANCELLED,
    ApplicationStatus.OWN_FUNDS,
    ApplicationStatus.EXTERNAL_CREDIT_APPROVED,
)
# Cierre → modalidad de financiación que debe estar registrada.
CLOSING_FINANCING_MODES: dict[str, str] = {
    ApplicationStatus.OWN_FUNDS: OWN_FUNDS,
    ApplicationStatus.EXTERNAL_CREDIT_APPROVED: EXTERNAL_CREDIT,
}
DOCUMENTS_NOT_VERIFIED_MESSAGE = (
    "Los documentos obligatorios todavía no se pueden verificar: el expediente documental "
    "aún no está disponible."
)


@dataclass(frozen=True)
class StatusChange:
    application: CreditApplication
    previous_status: str
    transitioned_at: datetime


def documents_verified(application: CreditApplication) -> bool:
    """Parte documental de `APPLICATION_READY_TO_FILE` y de la completitud.

    Falla cerrada hasta que exista el expediente documental (paso 10).
    """
    return False


def _lock_for_status_change(
    application: CreditApplication, expected_version: int
) -> CreditApplication:
    """Bloquea la fila. Terminada: ``409 APPLICATION_CLOSED``; otra versión:
    ``409 STALE_VERSION``. A diferencia de ``lock_for_edit``, admite estados posteriores
    a `FILED` (el desistimiento y las transiciones del paso 11)."""
    locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
    if locked.is_terminal:
        raise ApplicationClosed()
    ensure_version(locked.version, expected_version)
    return locked


def _ensure_financing_mode(locked: CreditApplication, to_status: str) -> None:
    required = CLOSING_FINANCING_MODES.get(to_status)
    if required is None:
        return
    mode = (
        FinancingPreference.objects.filter(application=locked)
        .values_list("financing_mode_item__code", flat=True)
        .first()
    )
    if mode != required:
        raise FinancingModeMismatch(
            details=[
                {
                    "field": "financing_mode_code",
                    "code": "FINANCING_MODE_MISMATCH",
                    "message": (
                        f"Para pasar a {to_status}, registra la financiación con la "
                        f"modalidad {required} en `/financing`."
                    ),
                }
            ]
        )


def _ready_to_file_problems(actor: User, locked: CreditApplication) -> list[dict[str, Any]]:
    """Motivos por los que no cumple `APPLICATION_READY_TO_FILE`; vacío si la cumple.

    Si la última evaluación no corresponde a la versión y al producto actuales, evalúa
    y la guarda: la evaluación se conserva aunque la transición se rechace.
    """
    problems: list[dict[str, Any]] = []
    if locked.bank_product_id is None:
        problems.append(
            {
                "field": "bank_product_id",
                "code": "BANK_PRODUCT_REQUIRED",
                "message": "Elige un producto bancario.",
            }
        )
    else:
        evaluation = latest_evaluation(locked)
        if evaluation is None or not is_current(evaluation, locked):
            evaluation = save_evaluation(actor, locked)
        for row in blocking_rows(evaluation.result_snapshot["rules"]):
            blocked = issue(row)
            problems.append(
                {
                    "field": blocked["field"],
                    "code": "BANK_RULE_BLOCKED",
                    "message": blocked["message"],
                }
            )
    if not documents_verified(locked):
        problems.append(
            {
                "field": "documents",
                "code": "DOCUMENTS_NOT_VERIFIED",
                "message": DOCUMENTS_NOT_VERIFIED_MESSAGE,
            }
        )
    return problems


def _apply_status_change(
    actor: User,
    locked: CreditApplication,
    transition: WorkflowTransition,
    *,
    reason: CatalogItem | None,
    comment: str,
) -> StatusChange:
    """Cambia el estado, sus fechas y la versión, y registra el historial."""
    now = timezone.now()
    previous = locked.status
    target = transition.to_status
    locked.status = target
    locked.current_stage_started_at = now
    fields = ["status", "current_stage_started_at"]
    if target == ApplicationStatus.READY_TO_FILE:
        locked.ready_to_file_at = now
        fields.append("ready_to_file_at")
    elif previous == ApplicationStatus.READY_TO_FILE and target in EDITABLE_APPLICATION_STATUSES:
        # Reabrir la revisión: deja de estar lista para radicar.
        locked.ready_to_file_at = None
        fields.append("ready_to_file_at")
    if target == ApplicationStatus.WITHDRAWN:
        locked.withdrawn_at = now
        locked.withdrawal_reason_item = reason
        fields += ["withdrawn_at", "withdrawal_reason_item"]
    if target in TERMINAL_APPLICATION_STATUSES:
        locked.closed_at = now
        fields.append("closed_at")
    bump_version(locked, fields)
    ApplicationStatusHistory.objects.create(
        application=locked,
        from_status=previous,
        to_status=target,
        transition=transition,
        reason_item=reason,
        comment=comment,
        actor_user=actor,
        application_version=locked.version,
    )
    return StatusChange(application=locked, previous_status=previous, transitioned_at=now)


def _notify_status_change(
    actor: User,
    change: StatusChange,
    transition: WorkflowTransition,
    reason: CatalogItem | None,
    comment: str,
) -> None:
    logger.info(
        "Solicitud %s: %s → %s (%s) por %s",
        change.application.code,
        change.previous_status,
        transition.to_status,
        transition.code,
        actor.pk,
    )
    application_status_changed.send(
        sender=CreditApplication,
        application=change.application,
        from_status=change.previous_status,
        to_status=transition.to_status,
        transition_code=transition.code,
        reason_code=reason.code if reason is not None else None,
        comment=comment,
        actor=actor,
    )


def transition_application(
    actor: User,
    application: CreditApplication,
    *,
    to_status: str,
    expected_version: int,
    reason: CatalogItem | None = None,
    comment: str = "",
) -> StatusChange:
    """Cambia el estado según las transiciones configuradas del flujo APPLICATION.

    - `WITHDRAWN` va por ``withdraw_application`` (``400``).
    - `CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` exigen motivo (``400``), y los
      dos últimos, la modalidad de financiación correspondiente
      (``422 FINANCING_MODE_MISMATCH``).
    - La guarda `APPLICATION_READY_TO_FILE` responde ``422 APPLICATION_NOT_READY`` con
      todos los motivos en ``details``.
    """
    if to_status == ApplicationStatus.WITHDRAWN:
        raise ValidationError(
            {"target_status": ["Para desistir usa POST /applications/{id}/withdrawals."]}
        )
    if to_status in REASON_REQUIRED_STATUSES and reason is None:
        raise ValidationError({"reason_code": [f"El motivo es obligatorio para {to_status}."]})

    problems: list[dict[str, Any]] = []
    change: StatusChange | None = None
    with transaction.atomic():
        locked = _lock_for_status_change(application, expected_version)
        transition = resolve_transition(
            actor, flow_type=FlowType.APPLICATION, from_status=locked.status, to_status=to_status
        )
        _ensure_financing_mode(locked, to_status)
        if transition.guard_code == READY_TO_FILE_GUARD:
            problems = _ready_to_file_problems(actor, locked)
        if not problems:
            change = _apply_status_change(actor, locked, transition, reason=reason, comment=comment)
    if problems:
        # Fuera del bloque: la evaluación que guardó la guarda queda confirmada.
        raise ApplicationNotReady(details=problems)
    assert change is not None
    _notify_status_change(actor, change, transition, reason, comment)
    return change


def withdraw_application(
    actor: User,
    application: CreditApplication,
    *,
    expected_version: int,
    reason: CatalogItem,
    comment: str = "",
) -> StatusChange:
    """Registra el desistimiento con una transición `WITHDRAW_<estado>`.

    Se admite desde cualquier estado no terminal, también después de `FILED`.
    """
    with transaction.atomic():
        locked = _lock_for_status_change(application, expected_version)
        transition = resolve_transition(
            actor,
            flow_type=FlowType.APPLICATION,
            from_status=locked.status,
            to_status=ApplicationStatus.WITHDRAWN,
        )
        change = _apply_status_change(actor, locked, transition, reason=reason, comment=comment)
    _notify_status_change(actor, change, transition, reason, comment)
    return change


def available_actions(user: User, application: CreditApplication) -> list[WorkflowTransition]:
    """Transiciones que ``user`` puede ejecutar desde el estado actual (rol y permiso).

    La guarda no se evalúa. Incluye `WITHDRAW_*`, que se ejecutan por `/withdrawals`.
    """
    return list(
        available_transitions(user, flow_type=FlowType.APPLICATION, from_status=application.status)
    )


def status_history_queryset(application: CreditApplication) -> QuerySet[ApplicationStatusHistory]:
    return (
        ApplicationStatusHistory.objects.filter(application=application)
        .select_related("transition", "reason_item", "actor_user")
        .order_by("-created_at", "-application_version")
    )


# --------------------------------------------------------------------------------------
# Completitud
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletenessItem:
    code: str
    complete: bool
    message: str
    participant_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Completeness:
    percentage: int
    ready_to_file: bool
    items: list[CompletenessItem]
    documents_verified: bool
    documents_message: str


def _bank_items(application: CreditApplication) -> list[CompletenessItem]:
    if application.bank_product_id is None:
        return [
            CompletenessItem("bank_product", False, "Elige un producto bancario."),
            CompletenessItem(
                "bank_evaluation", False, "Elige un producto para evaluar sus reglas."
            ),
        ]
    evaluation = latest_evaluation(application)
    if evaluation is None:
        evaluated = CompletenessItem("bank_evaluation", False, "Evalúa las reglas del banco.")
    elif not is_current(evaluation, application):
        evaluated = CompletenessItem(
            "bank_evaluation",
            False,
            "La última evaluación no corresponde a los datos actuales: evalúa de nuevo.",
        )
    elif not evaluation.is_eligible:
        evaluated = CompletenessItem(
            "bank_evaluation", False, "La última evaluación tiene reglas bloqueantes."
        )
    else:
        evaluated = CompletenessItem(
            "bank_evaluation", True, "Las reglas del banco no tienen bloqueos."
        )
    return [CompletenessItem("bank_product", True, "Producto bancario elegido."), evaluated]


def completeness(application: CreditApplication) -> Completeness:
    """Datos que faltan para radicar. Los documentos no cuentan hasta el paso 10."""
    has_property = Property.objects.filter(application=application).exists()
    mode = (
        FinancingPreference.objects.filter(application=application)
        .values_list("financing_mode_item__code", flat=True)
        .first()
    )
    items = [
        CompletenessItem(
            "property",
            has_property,
            "Inmueble registrado." if has_property else "Registra el inmueble.",
        ),
        CompletenessItem(
            "financing",
            mode is not None,
            "Financiación registrada." if mode is not None else "Registra la financiación.",
        ),
    ]
    if mode in (None, BANK_CREDIT):
        items += _bank_items(application)
    contributors = (
        participants_queryset()
        .filter(application=application, is_active=True, contributes_income=True)
        .select_related("financial_profile")
    )
    for participant in contributors:
        has_profile = hasattr(participant, "financial_profile")
        name = participant.client.full_name
        items.append(
            CompletenessItem(
                "financial_profile",
                has_profile,
                f"Perfil financiero de {name} registrado."
                if has_profile
                else f"Registra el perfil financiero de {name}.",
                participant_id=participant.pk,
            )
        )
    percentage = sum(item.complete for item in items) * 100 // len(items)
    verified = documents_verified(application)
    return Completeness(
        percentage=percentage,
        ready_to_file=percentage == 100 and verified,
        items=items,
        documents_verified=verified,
        documents_message=DOCUMENTS_NOT_VERIFIED_MESSAGE,
    )
