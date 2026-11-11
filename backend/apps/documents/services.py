"""Casos de uso de la configuración documental: tipos y requisitos (sección 23.4 de la API).

Acceso, igual que la configuración bancaria (``/banks``):

- ``document_requirements.read``: ``ADMIN`` y ``ADVISOR``. Cubre también
  ``/document-types``.
- Crear, editar y publicar: solo ``ADMIN``.
- ``INDEPENDENT_BROKER`` y ``CONSTRUCTION_PARTNER`` no consultan esta configuración.
  El comprador conocerá formatos y tamaños en el paso 10, a través de los slots de su
  propia solicitud, no del catálogo general.

Un requisito lógico es su alcance (``SCOPE_FIELDS``) y cada fila es una versión, con
las mismas reglas de versionado que ``bank_policy_rules``. ``applicable_requirements``
y ``preview_checklist`` son el punto de partida del paso 10, que materializará la
lista como ``application_document_slots``.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.banking.models import BankProduct, BankProductPurpose
from apps.catalogs.exceptions import DuplicateCode, InvalidStateTransition
from apps.catalogs.models import CatalogItem
from apps.documents.exceptions import (
    DocumentTypeInactive,
    RequirementDraftExists,
    RequirementExpired,
    RequirementScopeExists,
)
from apps.documents.models import (
    SCOPE_FIELDS,
    DocumentRequirement,
    DocumentType,
    HolderScope,
    RequirementStatus,
)
from apps.documents.signals import (
    document_requirement_status_changed,
    document_type_status_changed,
)
from apps.identity.models import User

logger = logging.getLogger(__name__)

# Estados en los que un requisito puede llegar a aplicarse a una solicitud.
_LIVE_STATUSES = (RequirementStatus.DRAFT, RequirementStatus.ACTIVE)


def _lock_document_type(document_type_id: uuid.UUID) -> None:
    """Serializa los cambios de requisitos de un tipo (versiones y publicación).

    Todas las versiones de un alcance comparten tipo documental.
    """
    DocumentType.objects.select_for_update().filter(pk=document_type_id).first()


# --------------------------------------------------------------------------------------
# Tipos documentales
# --------------------------------------------------------------------------------------


def document_types_queryset() -> QuerySet[DocumentType]:
    return DocumentType.objects.all()


def create_document_type(data: dict[str, Any]) -> DocumentType:
    try:
        with transaction.atomic():
            return DocumentType.objects.create(**data)
    except IntegrityError as exc:
        raise DuplicateCode("Ya existe un tipo documental con ese código.") from exc


def update_document_type(document_type: DocumentType, changes: dict[str, Any]) -> DocumentType:
    """El código no se edita. Un tipo deja de ser repetible solo si ningún requisito
    vigente o en borrador pide más de un archivo, y cambia de titular solo si no tiene
    requisitos vigentes ni en borrador."""
    if not changes:
        return document_type
    with transaction.atomic():
        _lock_document_type(document_type.pk)
        new_scope = changes.get("holder_scope")
        if new_scope is not None and new_scope != document_type.holder_scope:
            live = DocumentRequirement.objects.filter(
                document_type=document_type, status__in=_LIVE_STATUSES
            ).exists()
            if live:
                raise ValidationError(
                    {
                        "holder_scope": [
                            "Hay requisitos activos o en borrador de este tipo: desactívalos "
                            "antes de cambiar a quién pertenece el documento."
                        ]
                    }
                )
        if changes.get("is_repeatable") is False:
            multi_file = DocumentRequirement.objects.filter(
                document_type=document_type, status__in=_LIVE_STATUSES, minimum_files__gt=1
            ).exists()
            if multi_file:
                raise ValidationError(
                    {
                        "is_repeatable": [
                            "Hay requisitos activos o en borrador que piden más de un archivo "
                            "de este tipo."
                        ]
                    }
                )
        for name, value in changes.items():
            setattr(document_type, name, value)
        document_type.save(update_fields=[*changes, "updated_at"])
    return document_type


def set_document_type_active(
    document_type: DocumentType, *, active: bool, actor: User, reason: str = ""
) -> DocumentType:
    """Un tipo inactivo deja de pedirse en solicitudes nuevas y sus requisitos no se
    pueden publicar. No altera el historial ni los expedientes ya armados."""
    if document_type.is_active == active:
        return document_type
    document_type.is_active = active
    document_type.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "Tipo documental %s: is_active=%s por %s. Motivo: %s",
        document_type.code,
        active,
        actor.pk,
        reason or "-",
    )
    document_type_status_changed.send(
        sender=DocumentType,
        document_type=document_type,
        is_active=active,
        actor=actor,
        reason=reason,
    )
    return document_type


# --------------------------------------------------------------------------------------
# Requisitos
# --------------------------------------------------------------------------------------


def requirements_queryset() -> QuerySet[DocumentRequirement]:
    return DocumentRequirement.objects.select_related(
        "bank_product__bank",
        "document_type",
        "purpose_item",
        "employment_profile_item",
        "property_condition_item",
    )


def _scope_of(requirement: DocumentRequirement) -> dict[str, Any]:
    """Alcance (``SCOPE_FIELDS``) por columna, sin cargar las relaciones.

    Sirve para filtrar (``campo=None`` se traduce en ``IS NULL``) y para crear.
    """
    return {
        "bank_product_id": requirement.bank_product_id,
        "document_type_id": requirement.document_type_id,
        "purpose_item_id": requirement.purpose_item_id,
        "employment_profile_item_id": requirement.employment_profile_item_id,
        "participant_role": requirement.participant_role,
        "property_condition_item_id": requirement.property_condition_item_id,
    }


def _family(requirement: DocumentRequirement) -> QuerySet[DocumentRequirement]:
    """Todas las versiones del mismo alcance."""
    return DocumentRequirement.objects.filter(**_scope_of(requirement))


def _check_validity(valid_from: datetime, valid_to: datetime | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise ValidationError({"valid_to": ["Debe ser mayor o igual que valid_from."]})


def _check_minimum_files(document_type: DocumentType, minimum_files: int) -> None:
    if minimum_files > 1 and not document_type.is_repeatable:
        raise ValidationError(
            {"minimum_files": ["El tipo documental no es repetible: solo admite un archivo."]}
        )


def _check_holder_scope(
    document_type: DocumentType,
    participant_role: str | None,
    employment_profile: CatalogItem | None,
) -> None:
    """Un documento de la solicitud se pide una sola vez: no depende del participante."""
    if document_type.holder_scope != HolderScope.APPLICATION:
        return
    message = "El documento es de la solicitud, no de un participante: deja este campo vacío."
    errors: dict[str, list[str]] = {}
    if participant_role is not None:
        errors["participant_role"] = [message]
    if employment_profile is not None:
        errors["employment_profile_code"] = [message]
    if errors:
        raise ValidationError(errors)


def _check_purpose_admitted(product: BankProduct | None, purpose: CatalogItem | None) -> None:
    if product is None or purpose is None:
        return
    admitted = BankProductPurpose.objects.filter(
        bank_product=product, purpose_item=purpose, is_active=True
    ).exists()
    if not admitted:
        raise ValidationError({"purpose_code": ["El producto no admite esa finalidad."]})


def _version_ref(requirement: DocumentRequirement, code: str, message: str) -> dict[str, Any]:
    return {"field": None, "code": code, "message": message, "resource_id": str(requirement.pk)}


def create_requirement(data: dict[str, Any]) -> DocumentRequirement:
    """Crea la versión 1 de un requisito, en borrador.

    Si el alcance ya existe responde ``409 REQUIREMENT_SCOPE_EXISTS`` con el id de su
    última versión: los cambios se hacen con ``PATCH`` sobre ella.
    """
    data.setdefault("valid_from", timezone.now())
    data.setdefault("minimum_files", 1)
    document_type: DocumentType = data["document_type"]
    _check_validity(data["valid_from"], data.get("valid_to"))
    _check_minimum_files(document_type, data["minimum_files"])
    _check_holder_scope(
        document_type, data.get("participant_role"), data.get("employment_profile_item")
    )
    _check_purpose_admitted(data.get("bank_product"), data.get("purpose_item"))

    scope = {name: data.get(name) for name in SCOPE_FIELDS}
    try:
        with transaction.atomic():
            _lock_document_type(document_type.pk)
            latest = DocumentRequirement.objects.filter(**scope).order_by("-version").first()
            if latest is not None:
                raise RequirementScopeExists(
                    details=[
                        _version_ref(
                            latest, "EXISTING_REQUIREMENT", f"Edita la versión v{latest.version}."
                        )
                    ]
                )
            return DocumentRequirement.objects.create(
                **data, version=1, status=RequirementStatus.DRAFT
            )
    except IntegrityError as exc:
        raise RequirementScopeExists() from exc


# Lo que se puede cambiar de una versión. El alcance nunca se edita: si cambia, es un
# requisito nuevo y el anterior se desactiva.
EDITABLE_REQUIREMENT_FIELDS: tuple[str, ...] = (
    "is_required",
    "is_waivable",
    "minimum_files",
    "alternative_group_code",
    "validity_days",
    "sort_order",
    "valid_from",
    "valid_to",
)


def update_requirement(
    requirement: DocumentRequirement, changes: dict[str, Any]
) -> tuple[DocumentRequirement, bool]:
    """Edita un borrador o, sobre una versión publicada, crea un borrador nuevo.

    Devuelve el requisito resultante y si se creó una versión. La versión publicada
    (``ACTIVE`` o ``INACTIVE``) nunca se modifica. Solo existe un borrador por
    alcance: si ya hay uno, responde ``409 REQUIREMENT_DRAFT_EXISTS`` con su id.
    """
    if not changes:
        return requirement, False

    with transaction.atomic():
        _lock_document_type(requirement.document_type_id)
        requirement.refresh_from_db()
        values = {name: getattr(requirement, name) for name in EDITABLE_REQUIREMENT_FIELDS}
        values.update(changes)
        _check_validity(values["valid_from"], values["valid_to"])
        _check_minimum_files(requirement.document_type, values["minimum_files"])

        if requirement.status == RequirementStatus.DRAFT:
            for name, value in changes.items():
                setattr(requirement, name, value)
            requirement.save(update_fields=[*changes, "updated_at"])
            return requirement, False

        # El tipo pudo cambiar de titular mientras esta versión estaba inactiva.
        _check_holder_scope(
            requirement.document_type,
            requirement.participant_role,
            requirement.employment_profile_item,
        )
        family = _family(requirement)
        draft = family.filter(status=RequirementStatus.DRAFT).first()
        if draft is not None:
            raise RequirementDraftExists(
                details=[
                    _version_ref(draft, "EXISTING_DRAFT", f"Edita el borrador v{draft.version}.")
                ]
            )
        latest = family.aggregate(latest=Max("version"))["latest"]
        new_version = DocumentRequirement.objects.create(
            **_scope_of(requirement), **values, version=latest + 1, status=RequirementStatus.DRAFT
        )
    logger.info(
        "Requisito %s: borrador v%s creado desde v%s",
        requirement.pk,
        new_version.version,
        requirement.version,
    )
    return new_version, True


def _notify_requirement_status(
    requirement: DocumentRequirement, from_status: str, actor: User
) -> None:
    logger.info(
        "Requisito %s v%s: %s → %s por %s",
        requirement.pk,
        requirement.version,
        from_status,
        requirement.status,
        actor.pk,
    )
    document_requirement_status_changed.send(
        sender=DocumentRequirement,
        requirement=requirement,
        from_status=from_status,
        to_status=requirement.status,
        actor=actor,
    )


def activate_requirement(actor: User, requirement: DocumentRequirement) -> DocumentRequirement:
    """Publica una versión. La versión ``ACTIVE`` anterior del alcance pasa a ``INACTIVE``.

    Exige que el tipo documental esté activo y que la vigencia no haya terminado.
    """
    with transaction.atomic():
        _lock_document_type(requirement.document_type_id)
        requirement.refresh_from_db()
        if requirement.status == RequirementStatus.ACTIVE:
            return requirement
        if not requirement.document_type.is_active:
            raise DocumentTypeInactive()
        if requirement.valid_to is not None and requirement.valid_to < timezone.now():
            raise RequirementExpired()

        previous = _family(requirement).filter(status=RequirementStatus.ACTIVE).first()
        if previous is not None:
            previous.status = RequirementStatus.INACTIVE
            previous.save(update_fields=["status", "updated_at"])
        from_status = requirement.status
        requirement.status = RequirementStatus.ACTIVE
        requirement.save(update_fields=["status", "updated_at"])

    if previous is not None:
        _notify_requirement_status(previous, RequirementStatus.ACTIVE, actor)
    _notify_requirement_status(requirement, from_status, actor)
    return requirement


def deactivate_requirement(actor: User, requirement: DocumentRequirement) -> DocumentRequirement:
    """Deja de pedir el documento en casos futuros; los expedientes armados no cambian."""
    with transaction.atomic():
        _lock_document_type(requirement.document_type_id)
        requirement.refresh_from_db()
        if requirement.status == RequirementStatus.INACTIVE:
            return requirement
        if requirement.status == RequirementStatus.DRAFT:
            raise InvalidStateTransition("Un borrador no está publicado: no se puede desactivar.")
        requirement.status = RequirementStatus.INACTIVE
        requirement.save(update_fields=["status", "updated_at"])
    _notify_requirement_status(requirement, RequirementStatus.ACTIVE, actor)
    return requirement


# --------------------------------------------------------------------------------------
# Lista documental aplicable
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParticipantCase:
    role: str
    employment_profile: CatalogItem | None = None


@dataclass(frozen=True)
class ChecklistCase:
    bank_product: BankProduct | None
    participants: list[ParticipantCase]
    purpose: CatalogItem | None = None
    property_condition: CatalogItem | None = None
    at: datetime | None = None


@dataclass(frozen=True)
class ParticipantChecklist:
    index: int
    role: str
    employment_profile: CatalogItem | None
    requirements: list[DocumentRequirement]


@dataclass(frozen=True)
class ChecklistPreview:
    participants: list[ParticipantChecklist]
    # Documentos de la solicitud (`holder_scope = APPLICATION`): se piden una sola vez.
    application_requirements: list[DocumentRequirement]


def is_application_document(requirement: DocumentRequirement) -> bool:
    return requirement.document_type.holder_scope == HolderScope.APPLICATION


def _matches(field: str, value: Any) -> Q:
    """Un campo de alcance vacío aplica a cualquier valor; uno lleno, solo al suyo.

    Si el caso no trae el dato (``value`` es ``None``), solo aplican los vacíos.
    """
    if value is None:
        return Q(**{f"{field}__isnull": True})
    return Q(**{f"{field}__isnull": True}) | Q(**{field: value})


def applicable_requirements(
    *,
    bank_product: BankProduct | None,
    purpose: CatalogItem | None = None,
    property_condition: CatalogItem | None = None,
    at: datetime | None = None,
) -> QuerySet[DocumentRequirement]:
    """Versiones publicadas, vigentes en ``at`` y con tipo activo, para la solicitud.

    Incluye los requisitos generales (sin producto). Rol y perfil laboral dependen de
    cada participante: se filtran después con ``requirement_applies_to``.
    """
    moment = at or timezone.now()
    return (
        requirements_queryset()
        .filter(
            _matches("bank_product", bank_product),
            _matches("purpose_item", purpose),
            _matches("property_condition_item", property_condition),
            Q(valid_to__isnull=True) | Q(valid_to__gte=moment),
            status=RequirementStatus.ACTIVE,
            valid_from__lte=moment,
            document_type__is_active=True,
        )
        .order_by("sort_order", "document_type__code")
    )


def requirement_applies_to(requirement: DocumentRequirement, participant: ParticipantCase) -> bool:
    if requirement.participant_role not in (None, participant.role):
        return False
    if requirement.employment_profile_item_id is None:
        return True
    profile = participant.employment_profile
    return profile is not None and requirement.employment_profile_item_id == profile.pk


def preview_checklist(case: ChecklistCase) -> ChecklistPreview:
    """Simula la lista documental de una solicitud sin tocar datos (una sola consulta).

    Cada participante recibe los requisitos que le aplican; los documentos de la
    solicitud van aparte. Los requisitos sin producto son generales y aplican a
    cualquier banco.
    """
    candidates = list(
        applicable_requirements(
            bank_product=case.bank_product,
            purpose=case.purpose,
            property_condition=case.property_condition,
            at=case.at,
        )
    )
    per_participant = [req for req in candidates if not is_application_document(req)]
    return ChecklistPreview(
        participants=[
            ParticipantChecklist(
                index=index,
                role=participant.role,
                employment_profile=participant.employment_profile,
                requirements=[
                    req for req in per_participant if requirement_applies_to(req, participant)
                ],
            )
            for index, participant in enumerate(case.participants)
        ],
        application_requirements=[req for req in candidates if is_application_document(req)],
    )
