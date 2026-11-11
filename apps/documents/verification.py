"""Cumplimiento del expediente documental (decisiones 7, 21, 22 y 24; acordadas 7 y 8;
Tanda 4, decisiones 30 a 34).

Lo usan la guarda de `READY_TO_FILE`, la completitud, el progreso del comprador y el
paquete. Solo cuentan los slots vigentes y obligatorios:

- un slot está **cumplido** si está ``WAIVED`` o ``APPROVED`` y su versión vigente no
  venció (``expires_at`` nulo o posterior a hoy);
- un **grupo alternativo** (mismo titular y ``alternative_group_code``) cuenta como un
  solo obligatorio y se cumple con un juego completo de un mismo tipo: todos los slots
  de ese tipo del grupo cumplidos;
- sin obligatorios, el expediente no está verificado (``DOCUMENTS_NOT_CONFIGURED``) y el
  porcentaje es 0.

``details`` de la guarda (decisiones 21 y 33): un slot suelto vencido da
``DOCUMENT_EXPIRED``; uno sin cumplir, ``DOCUMENT_PENDING``. Un grupo sin cumplir da un
``DOCUMENT_PENDING`` (``resource_id`` = su primer slot) y un ``DOCUMENT_EXPIRED`` por
cada aprobado vencido del grupo; un grupo cumplido no da nada.

No importa ``applications.services``: este lo usa.
"""

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.documents.dossier_serializers import slot_label
from apps.documents.models import ApplicationDocumentSlot, SlotStatus

DOCUMENTS_FIELD = "documents"
NOT_CONFIGURED_MESSAGE = (
    "La solicitud no tiene documentos obligatorios: revisa los requisitos documentales del "
    "producto elegido."
)


@dataclass(frozen=True)
class SlotCheck:
    """Un slot obligatorio en el detalle de la completitud. ``complete`` dice si cuenta
    como cumplido: en un grupo alternativo, si el grupo está cumplido."""

    slot_id: uuid.UUID
    participant_id: uuid.UUID | None
    document_type_code: str
    document_type_name: str
    label: str
    status: str
    alternative_group_code: str | None
    expires_at: date | None
    complete: bool


@dataclass(frozen=True)
class DossierCheck:
    required_total: int
    completed_total: int
    slots: list[SlotCheck]
    problems: list[dict[str, Any]] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return not self.problems

    @property
    def percentage(self) -> int:
        if not self.required_total:
            return 0
        return self.completed_total * 100 // self.required_total

    @property
    def message(self) -> str:
        if not self.required_total:
            return NOT_CONFIGURED_MESSAGE
        if self.verified:
            return "Los documentos obligatorios están completos."
        missing = self.required_total - self.completed_total
        return f"Faltan {missing} de {self.required_total} documentos obligatorios."


def is_expired(slot: ApplicationDocumentSlot, today: date) -> bool:
    """Aprobado con la versión vigente vencida (``expires_at <= hoy``, decisión 34)."""
    version = slot.current_file
    return (
        slot.status == SlotStatus.APPROVED
        and version is not None
        and version.expires_at is not None
        and version.expires_at <= today
    )


def is_fulfilled(slot: ApplicationDocumentSlot, today: date) -> bool:
    if slot.status == SlotStatus.WAIVED:
        return True
    return slot.status == SlotStatus.APPROVED and not is_expired(slot, today)


def _active_slots(application: CreditApplication, *, lock: bool) -> list[ApplicationDocumentSlot]:
    """Slots vigentes. Con ``lock``, bloquea todos en orden de id (decisión 22), después
    de la solicitud, que ya bloqueó quien llama."""
    slots = ApplicationDocumentSlot.objects.filter(
        application=application, retired_at__isnull=True
    ).select_related("document_type", "participant__client", "current_file")
    if lock:
        return list(slots.select_for_update(of=("self",)).order_by("pk"))
    return list(slots)


def presentation_order(slot: ApplicationDocumentSlot) -> tuple[Any, ...]:
    """El orden de ``dossier.slots_queryset``: la solicitud primero, después cada
    participante en el orden en que entró."""
    participant = slot.participant
    return (
        participant is not None,
        participant.created_at if participant is not None else None,
        slot.sort_order,
        slot.document_type.code,
        slot.slot_index,
        slot.created_at,
    )


def _holder(slot: ApplicationDocumentSlot) -> str:
    participant = slot.participant
    return participant.client.full_name if participant is not None else "la solicitud"


def _pending(slot: ApplicationDocumentSlot, label: str) -> dict[str, Any]:
    return {
        "field": DOCUMENTS_FIELD,
        "code": "DOCUMENT_PENDING",
        "message": f"«{label}» de {_holder(slot)} no está aprobado ni exonerado.",
        "resource_id": str(slot.pk),
    }


def _group_pending(members: list[ApplicationDocumentSlot]) -> dict[str, Any]:
    first = members[0]
    names = list(dict.fromkeys(member.document_type.name for member in members))
    return {
        "field": DOCUMENTS_FIELD,
        "code": "DOCUMENT_PENDING",
        "message": (
            f"Falta un juego completo del grupo {first.alternative_group_code} de "
            f"{_holder(first)}: {' o '.join(names)}."
        ),
        "resource_id": str(first.pk),
    }


def _expired(slot: ApplicationDocumentSlot, label: str) -> dict[str, Any]:
    version = slot.current_file
    assert version is not None and version.expires_at is not None
    return {
        "field": DOCUMENTS_FIELD,
        "code": "DOCUMENT_EXPIRED",
        "message": (
            f"«{label}» de {_holder(slot)} venció el "
            f"{version.expires_at.isoformat()}: pide uno más reciente."
        ),
        "resource_id": str(slot.pk),
    }


def _group_fulfilled(members: Iterable[ApplicationDocumentSlot], today: date) -> bool:
    by_type: dict[uuid.UUID, list[bool]] = {}
    for member in members:
        by_type.setdefault(member.document_type_id, []).append(is_fulfilled(member, today))
    return any(all(states) for states in by_type.values())


def check_dossier(application: CreditApplication, *, lock: bool = False) -> DossierCheck:
    """Cumplimiento de los obligatorios. Con ``lock``, dentro de una transacción y con
    la solicitud ya bloqueada (guarda y paquete)."""
    today = timezone.localdate()
    active = _active_slots(application, lock=lock)
    # El "m" de "Nombre n de m": slots vigentes del mismo titular y tipo.
    sizes = Counter((slot.participant_id, slot.document_type_id) for slot in active)

    def label(slot: ApplicationDocumentSlot) -> str:
        return slot_label(slot, sizes[slot.participant_id, slot.document_type_id])

    required = sorted((slot for slot in active if slot.is_required), key=presentation_order)

    groups: dict[tuple[uuid.UUID | None, str], list[ApplicationDocumentSlot]] = {}
    for slot in required:
        if slot.alternative_group_code:
            groups.setdefault((slot.participant_id, slot.alternative_group_code), []).append(slot)

    problems: list[dict[str, Any]] = []
    checks: list[SlotCheck] = []
    required_total = completed_total = 0
    seen_groups: set[tuple[uuid.UUID | None, str]] = set()
    group_state: dict[tuple[uuid.UUID | None, str], bool] = {
        key: _group_fulfilled(members, today) for key, members in groups.items()
    }
    for slot in required:
        if slot.alternative_group_code:
            key = (slot.participant_id, slot.alternative_group_code)
            complete = group_state[key]
            if key not in seen_groups:
                seen_groups.add(key)
                required_total += 1
                completed_total += complete
                if not complete:
                    members = groups[key]
                    problems.append(_group_pending(members))
                    problems.extend(_expired(m, label(m)) for m in members if is_expired(m, today))
        else:
            complete = is_fulfilled(slot, today)
            required_total += 1
            completed_total += complete
            if is_expired(slot, today):
                problems.append(_expired(slot, label(slot)))
            elif not complete:
                problems.append(_pending(slot, label(slot)))
        version = slot.current_file
        checks.append(
            SlotCheck(
                slot_id=slot.pk,
                participant_id=slot.participant_id,
                document_type_code=slot.document_type.code,
                document_type_name=slot.document_type.name,
                label=label(slot),
                status=slot.status,
                alternative_group_code=slot.alternative_group_code,
                expires_at=version.expires_at if version is not None else None,
                complete=complete,
            )
        )
    if not required_total:
        problems.append(
            {
                "field": DOCUMENTS_FIELD,
                "code": "DOCUMENTS_NOT_CONFIGURED",
                "message": NOT_CONFIGURED_MESSAGE,
            }
        )
    return DossierCheck(
        required_total=required_total,
        completed_total=completed_total,
        slots=checks,
        problems=problems,
    )
