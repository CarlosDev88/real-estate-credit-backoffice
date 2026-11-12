"""Materialización y recálculo del expediente documental (slots) de una solicitud.

``sync_slots(locked)`` convierte los requisitos publicados que aplican a la solicitud
en ``application_document_slots``. Se llama con la solicitud ya bloqueada y dentro de
la transacción del cambio que lo provoca (decisión 6): creación, producto, finalidad,
condición del inmueble, participantes y perfil laboral, y el ``refresh`` manual. Solo
antes de `FILED`: quien llama ya lo garantiza con ``lock_for_edit``.

Reglas (decisiones 17 y 20, acordadas 3, 4 y 5):

- Un requisito con ``minimum_files = n`` crea n slots (``slot_index`` 1..n).
- Los tipos con ``holder_scope = APPLICATION`` crean un solo juego, sin participante.
  Los demás, un juego por participante vigente al que aplique el requisito.
- Si dos requisitos piden el mismo tipo para el mismo titular, se crea un solo juego
  con la combinación más estricta.
- Un slot que deja de aplicar se retira (``retired_at``) sin borrarse; si vuelve a
  aplicar, revive con su historial. Si baja ``minimum_files``, se retiran los de mayor
  ``slot_index``.
- Un slot sin historial (``PENDING`` y sin versiones) se actualiza al requisito
  vigente; uno con historial conserva su snapshot.

El recálculo usa la configuración publicada en ese momento: un requisito desactivado,
vencido o de un tipo inactivo deja de aplicar y su slot se retira en el siguiente
recálculo (no al desactivarlo).
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, CreditApplication, Property
from apps.catalogs.models import CatalogItem
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentRequirement,
    SlotStatus,
)
from apps.documents.services import (
    ParticipantCase,
    applicable_requirements,
    is_application_document,
    requirement_applies_to,
)

logger = logging.getLogger(__name__)

# Titular (participante, o ``None`` para la solicitud) y tipo documental.
SetKey = tuple[uuid.UUID | None, uuid.UUID]
# Titular, tipo y ``slot_index``: lo que identifica a un slot vigente (decisión 20).
SlotKey = tuple[uuid.UUID | None, uuid.UUID, int]

# Campos del slot que se copian del requisito.
SNAPSHOT_FIELDS: tuple[str, ...] = (
    "requirement_id",
    "requirement_version",
    "is_required",
    "is_waivable",
    "minimum_files",
    "alternative_group_code",
    "validity_days",
    "sort_order",
)


@dataclass(frozen=True)
class SlotSpec:
    """Lo que debe copiarse a cada slot de un juego (titular + tipo)."""

    requirement_id: uuid.UUID
    requirement_version: int
    is_required: bool
    is_waivable: bool
    minimum_files: int
    alternative_group_code: str | None
    validity_days: int | None
    sort_order: int

    def snapshot(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in SNAPSHOT_FIELDS}


@dataclass
class SlotSync:
    """Resultado del recálculo: ids de los slots afectados."""

    created: list[uuid.UUID] = field(default_factory=list)
    retired: list[uuid.UUID] = field(default_factory=list)
    revived: list[uuid.UUID] = field(default_factory=list)
    updated: list[uuid.UUID] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.retired or self.revived or self.updated)


def _strictness(requirement: DocumentRequirement) -> tuple[Any, ...]:
    """Orden para elegir el requisito más estricto de un tipo repetido (decisión 17).

    Obligatorio, más archivos, vigencia más corta (con vigencia antes que sin ella) y
    no exonerable. El último criterio solo desempata para que la elección sea estable.
    """
    validity = requirement.effective_validity_days
    return (
        requirement.is_required,
        requirement.minimum_files,
        validity is not None,
        -(validity or 0),
        not requirement.is_waivable,
        -requirement.sort_order,
        str(requirement.pk),
    )


def merge_requirements(requirements: list[DocumentRequirement]) -> SlotSpec:
    """Combinación más estricta de los requisitos que piden el mismo tipo al mismo titular.

    Obligatorio si alguno lo es, el mayor ``minimum_files``, la menor vigencia y
    exonerable solo si todos lo son. El slot apunta al más estricto y toma su orden.
    Queda en un grupo alternativo solo si todos los requisitos lo están: un requisito
    fuera de grupo exige el documento por sí mismo.
    """
    strictest = max(requirements, key=_strictness)
    validities = [
        days for days in (req.effective_validity_days for req in requirements) if days is not None
    ]
    in_group = all(req.alternative_group_code for req in requirements)
    return SlotSpec(
        requirement_id=strictest.pk,
        requirement_version=strictest.version,
        is_required=any(req.is_required for req in requirements),
        is_waivable=all(req.is_waivable for req in requirements),
        minimum_files=max(req.minimum_files for req in requirements),
        alternative_group_code=strictest.alternative_group_code if in_group else None,
        validity_days=min(validities) if validities else None,
        sort_order=strictest.sort_order,
    )


def _employment_profile(participant: ApplicationParticipant) -> CatalogItem | None:
    profile = getattr(participant, "financial_profile", None)
    return None if profile is None else profile.employment_profile_item


def desired_slots(application: CreditApplication) -> dict[SetKey, SlotSpec]:
    """Juegos de slots que la configuración vigente exige hoy a la solicitud."""
    prop = Property.objects.select_related("condition_item").filter(application=application).first()
    candidates = list(
        applicable_requirements(
            bank_product=application.bank_product,
            purpose=application.purpose_item,
            property_condition=None if prop is None else prop.condition_item,
        )
    )
    participants = [
        (participant.pk, ParticipantCase(participant.role, _employment_profile(participant)))
        for participant in ApplicationParticipant.objects.filter(
            application=application, is_active=True
        ).select_related("financial_profile__employment_profile_item")
    ]

    grouped: dict[SetKey, list[DocumentRequirement]] = defaultdict(list)
    for requirement in candidates:
        if is_application_document(requirement):
            grouped[(None, requirement.document_type_id)].append(requirement)
            continue
        for participant_id, case in participants:
            if requirement_applies_to(requirement, case):
                grouped[(participant_id, requirement.document_type_id)].append(requirement)
    return {key: merge_requirements(requirements) for key, requirements in grouped.items()}


def _untouched(slot: ApplicationDocumentSlot) -> bool:
    """Sin historial: nadie cargó, revisó ni exoneró. Se puede actualizar al requisito."""
    return slot.status == SlotStatus.PENDING and not getattr(slot, "has_files", True)


def _apply_spec(slot: ApplicationDocumentSlot, spec: SlotSpec) -> bool:
    """Copia el snapshot al slot. Devuelve si cambió algo."""
    changed = False
    for name, value in spec.snapshot().items():
        if getattr(slot, name) != value:
            setattr(slot, name, value)
            changed = True
    return changed


def _pick_retired(candidates: list[ApplicationDocumentSlot]) -> ApplicationDocumentSlot:
    """Entre varios retirados en la misma posición, revive el que tiene historial y, si
    no, el más reciente."""
    return max(
        candidates,
        key=lambda slot: (not _untouched(slot), slot.retired_at or slot.created_at, str(slot.pk)),
    )


def sync_slots(locked: CreditApplication) -> SlotSync:
    """Alinea los slots de la solicitud con la configuración vigente.

    Llamar con la solicitud bloqueada y dentro de su transacción. Bloquea también sus
    slots, ordenados por id (decisión 22). No toca la versión de la solicitud
    (acordada 6).
    """
    desired = desired_slots(locked)
    existing: list[ApplicationDocumentSlot] = list(
        ApplicationDocumentSlot.objects.select_for_update()
        .filter(application=locked)
        .annotate(has_files=Exists(DocumentFile.objects.filter(slot=OuterRef("pk"))))
        .order_by("pk")
    )
    active: dict[SlotKey, ApplicationDocumentSlot] = {}
    retired: dict[SlotKey, list[ApplicationDocumentSlot]] = defaultdict(list)
    for slot in existing:
        key = (slot.participant_id, slot.document_type_id, slot.slot_index)
        if slot.retired_at is None:
            active[key] = slot
        else:
            retired[key].append(slot)

    result = SlotSync()
    now = timezone.now()

    def wanted(key: SlotKey) -> bool:
        spec = desired.get((key[0], key[1]))
        return spec is not None and key[2] <= spec.minimum_files

    to_retire = [slot for key, slot in active.items() if not wanted(key)]
    to_save: list[ApplicationDocumentSlot] = []
    to_create: list[ApplicationDocumentSlot] = []
    for (participant_id, document_type_id), spec in desired.items():
        for index in range(1, spec.minimum_files + 1):
            key = (participant_id, document_type_id, index)
            current = active.get(key)
            if current is not None:
                if _untouched(current) and _apply_spec(current, spec):
                    to_save.append(current)
                    result.updated.append(current.pk)
                continue
            if retired.get(key):
                revived = _pick_retired(retired[key])
                revived.retired_at = None
                if _untouched(revived):
                    _apply_spec(revived, spec)
                to_save.append(revived)
                result.revived.append(revived.pk)
                continue
            new_slot = ApplicationDocumentSlot(
                application=locked,
                participant_id=participant_id,
                document_type_id=document_type_id,
                slot_index=index,
                status=SlotStatus.PENDING,
                **spec.snapshot(),
            )
            to_create.append(new_slot)
            result.created.append(new_slot.pk)

    # Primero se retiran, para que un slot revivido o nuevo no choque con uno que sale.
    if to_retire:
        result.retired = [slot.pk for slot in to_retire]
        ApplicationDocumentSlot.objects.filter(pk__in=result.retired).update(
            retired_at=now, updated_at=now
        )
    if to_save:
        for slot in to_save:
            slot.updated_at = now
        ApplicationDocumentSlot.objects.bulk_update(
            to_save, [*SNAPSHOT_FIELDS, "retired_at", "updated_at"]
        )
    if to_create:
        ApplicationDocumentSlot.objects.bulk_create(to_create)

    if result.changed:
        logger.info(
            "Expediente de %s: %d slots creados, %d retirados, %d reactivados, %d actualizados",
            locked.code,
            len(result.created),
            len(result.retired),
            len(result.revived),
            len(result.updated),
        )
        # También cubre la creación de la solicitud y el recálculo manual. Import local:
        # `apps.applications.services` importa este módulo.
        from apps.applications.services import schedule_completeness_refresh

        schedule_completeness_refresh(locked.pk)
    return result
