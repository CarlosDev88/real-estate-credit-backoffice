"""Respuestas del banco a una radicación (API §20.2, REQUERIMIENTOS §4.5, paso 11).

Se registran a mano, solo contra la **última radicación** de la solicitud (``409
FILING_NOT_LATEST``), y son inmutables. Reglas por tipo (``RULES``): estados de la
solicitud admitidos (otro: ``409 INVALID_STATE_TRANSITION``), datos obligatorios
(``400``) y efecto.

- `RECEIVED`: `FILED` → `FILING_VALIDATION` (si ya está ahí, no cambia).
- `IN_ANALYSIS`: → `CREDIT_ANALYSIS`.
- `RETURNED`: → `BANK_OBSERVATION`. Por cada slot observado crea la observación y
  rechaza su versión vigente con el servicio de revisiones (el comprador la ve como
  "Corrígelo" con el mensaje). Solo esos slots se reemplazan después de `FILED`.
- `APPROVED`: → `APPROVED`, con monto y plazo.
- `REJECTED`: → `REJECTED` (cierra la solicitud).
- `DISBURSED`: desde `LEGALIZATION` → `DISBURSED`, con el monto desembolsado.
- `OTHER`: en cualquier estado no terminal, sin cambio de estado.

**Corrección** (``corrects_response``): solo de la última respuesta de la radicación,
del mismo tipo, y si es `RECEIVED`, `IN_ANALYSIS` u `OTHER` (``409
RESPONSE_CORRECTION_NOT_ALLOWED``). No cambia ningún estado.

La radicación toma el estado del tipo de la respuesta (salvo `OTHER` y las
correcciones). Todo va en una transacción que bloquea la solicitud, la radicación y los
slots observados (en orden de id). Después de confirmar se emiten
``application_status_changed`` (si cambió el estado) y ``filing_response_recorded``.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from rest_framework.exceptions import ValidationError

from apps.applications.models import CreditApplication
from apps.applications.services import (
    SystemStatusChange,
    applications_visible_to,
    apply_system_transition,
    lock_for_status_change,
    notify_system_transition,
)
from apps.catalogs.exceptions import InvalidStateTransition
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ApplicationStatus
from apps.documents import reviews
from apps.documents.models import ApplicationDocumentSlot, ReviewDecision, SlotStatus
from apps.filings.exceptions import FilingNotLatest, ResponseCorrectionNotAllowed
from apps.filings.models import (
    Filing,
    FilingResponse,
    FilingResponseObservation,
    FilingStatus,
)
from apps.filings.signals import filing_response_recorded
from apps.identity.models import User

logger = logging.getLogger(__name__)

RESPONSE_TYPE_CATALOG = "filing_response_type"

RECEIVED = "RECEIVED"
IN_ANALYSIS = "IN_ANALYSIS"
RETURNED = "RETURNED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
DISBURSED = "DISBURSED"
OTHER = "OTHER"

S = ApplicationStatus
SENT = (S.FILED, S.FILING_VALIDATION)
UNDER_REVIEW = (S.FILED, S.FILING_VALIDATION, S.CREDIT_ANALYSIS)

# Campos de la respuesta que solo admiten algunos tipos.
TYPED_FIELDS = (
    "reason_code",
    "observations",
    "approved_amount_cop",
    "approved_term_months",
    "valid_until",
    "disbursed_amount_cop",
)


@dataclass(frozen=True)
class ResponseRule:
    # Estados de la solicitud admitidos; ``None``: cualquiera no terminal.
    statuses: tuple[str, ...] | None
    # Estado al que pasa la solicitud; ``None``: no cambia.
    target: str | None
    filing_status: str | None
    required: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()
    # Catálogo de `reason_code`, si el tipo lo lleva.
    reason_catalog: str | None = None
    correctable: bool = False


RULES: dict[str, ResponseRule] = {
    RECEIVED: ResponseRule(SENT, S.FILING_VALIDATION, FilingStatus.RECEIVED, correctable=True),
    IN_ANALYSIS: ResponseRule(SENT, S.CREDIT_ANALYSIS, FilingStatus.IN_ANALYSIS, correctable=True),
    RETURNED: ResponseRule(
        UNDER_REVIEW,
        S.BANK_OBSERVATION,
        FilingStatus.RETURNED,
        required=("reason_code", "public_message", "observations"),
        allowed=("reason_code", "observations"),
        reason_catalog="filing_return_reason",
    ),
    APPROVED: ResponseRule(
        UNDER_REVIEW,
        S.APPROVED,
        FilingStatus.APPROVED,
        required=("approved_amount_cop", "approved_term_months", "public_message"),
        allowed=("approved_amount_cop", "approved_term_months", "valid_until"),
    ),
    REJECTED: ResponseRule(
        (*UNDER_REVIEW, S.BANK_OBSERVATION),
        S.REJECTED,
        FilingStatus.REJECTED,
        required=("reason_code", "public_message"),
        allowed=("reason_code",),
        reason_catalog="filing_rejection_reason",
    ),
    DISBURSED: ResponseRule(
        (S.LEGALIZATION,),
        S.DISBURSED,
        FilingStatus.DISBURSED,
        required=("disbursed_amount_cop",),
        allowed=("disbursed_amount_cop",),
    ),
    OTHER: ResponseRule(None, None, None, required=("internal_comment",), correctable=True),
}
RESPONSE_TYPES = tuple(RULES)


@dataclass(frozen=True)
class Observation:
    document_slot_id: uuid.UUID
    reason: CatalogItem
    message: str


@dataclass(frozen=True)
class ResponseInput:
    response_type: CatalogItem
    received_at: datetime
    external_reference: str | None = None
    reason: CatalogItem | None = None
    public_message: str | None = None
    internal_comment: str | None = None
    observations: list[Observation] = field(default_factory=list)
    approved_amount_cop: int | None = None
    approved_term_months: int | None = None
    valid_until: date | None = None
    disbursed_amount_cop: int | None = None
    corrects_response_id: uuid.UUID | None = None


# --- Consultas --------------------------------------------------------------------------


def responses_queryset() -> QuerySet[FilingResponse]:
    """Respuestas con lo que muestra la API, en orden cronológico."""
    return (
        FilingResponse.objects.select_related(
            "filing__application",
            "response_type_item",
            "reason_item",
            "evidence_file_object",
            "recorded_by",
        )
        .prefetch_related(
            Prefetch(
                "observations",
                queryset=FilingResponseObservation.objects.select_related("reason_item").order_by(
                    "created_at", "id"
                ),
            )
        )
        .order_by("received_at", "created_at", "id")
    )


def latest_public_update(application_id: uuid.UUID) -> FilingResponse | None:
    """La última respuesta con mensaje público de la solicitud, para el comprador."""
    return (
        FilingResponse.objects.select_related("response_type_item")
        .filter(filing__application_id=application_id, public_message__isnull=False)
        .exclude(public_message="")
        .order_by("-received_at", "-created_at", "-id")
        .first()
    )


# --- Validación -------------------------------------------------------------------------


def field_errors(code: str, values: dict[str, Any]) -> dict[str, list[str]]:
    """Errores de forma según el tipo: obligatorios vacíos y campos que no aplican.
    ``values`` trae los campos que envió el cliente (``None`` o vacío cuentan como no
    enviados). Lo usa el serializer."""
    rule = RULES[code]
    errors: dict[str, list[str]] = {}
    for name in rule.required:
        if values.get(name) in (None, "", []):
            errors[name] = [f"Es obligatorio para {code}."]
    for name in TYPED_FIELDS:
        if name not in rule.allowed and values.get(name) not in (None, "", []):
            errors[name] = [f"No aplica a {code}."]
    return errors


def _ensure_latest_filing(locked: CreditApplication, filing: Filing) -> None:
    latest = (
        Filing.objects.filter(application=locked)
        .order_by("-sequence_number")
        .values_list("pk", flat=True)
        .first()
    )
    if latest != filing.pk:
        raise FilingNotLatest()


def _ensure_correction(filing: Filing, code: str, corrected_id: uuid.UUID) -> FilingResponse:
    corrected = FilingResponse.objects.filter(filing=filing, pk=corrected_id).first()
    if corrected is None:
        raise ValidationError(
            {"corrects_response_id": ["La respuesta no existe en esta radicación."]}
        )
    last = FilingResponse.objects.filter(filing=filing).order_by("-created_at", "-id").first()
    same_type = corrected.response_type_item.code == code
    if last != corrected or not same_type or not RULES[code].correctable:
        raise ResponseCorrectionNotAllowed()
    return corrected


def _ensure_status(locked: CreditApplication, code: str) -> None:
    statuses = RULES[code].statuses
    if statuses is not None and locked.status not in statuses:
        raise InvalidStateTransition(
            f"Una respuesta {code} no se registra con la solicitud en {locked.status}."
        )


def _observed_slots(
    locked: CreditApplication, observations: list[Observation]
) -> dict[uuid.UUID, ApplicationDocumentSlot]:
    """Bloquea los slots observados en orden de id y valida que sean de la solicitud,
    estén vigentes, tengan una versión vigente y no estén exonerados."""
    ids = [item.document_slot_id for item in observations]
    errors: dict[str, list[str]] = {}
    if len(set(ids)) != len(ids):
        errors["observations"] = ["Cada documento se observa una sola vez."]
    slots = {
        slot.pk: slot
        for slot in ApplicationDocumentSlot.objects.select_for_update()
        .filter(application=locked, pk__in=ids, retired_at__isnull=True)
        .order_by("pk")
    }
    for index, item in enumerate(observations):
        slot = slots.get(item.document_slot_id)
        message = None
        if slot is None:
            message = "El documento no existe en esta solicitud."
        elif slot.current_file_id is None:
            message = "El documento no tiene una versión cargada."
        elif slot.status == SlotStatus.WAIVED:
            message = "El documento está exonerado."
        if message:
            errors[f"observations[{index}].document_slot_id"] = [message]
    if errors:
        raise ValidationError(errors)
    return slots


def _observe(
    actor: User,
    response: FilingResponse,
    slots: dict[uuid.UUID, ApplicationDocumentSlot],
    observations: list[Observation],
) -> None:
    """Crea las observaciones y después rechaza la versión vigente de cada slot: la
    revisión después de `FILED` exige la observación abierta."""
    ordered = sorted(observations, key=lambda item: item.document_slot_id)
    FilingResponseObservation.objects.bulk_create(
        [
            FilingResponseObservation(
                filing_response=response,
                document_slot_id=item.document_slot_id,
                reason_item=item.reason,
                buyer_message=item.message,
            )
            for item in ordered
        ]
    )
    note = f"Observación del banco en la radicación #{response.filing.sequence_number}."
    for item in ordered:
        slot = slots[item.document_slot_id]
        reviews.review_slot(
            actor,
            slot,
            reviews.Review(
                decision=ReviewDecision.REJECTED,
                document_file_id=slot.current_file_id,
                reason_item=item.reason,
                buyer_comment=item.message,
                internal_comment=note,
            ),
        )


# --- Registrar --------------------------------------------------------------------------


def record_response(
    actor: User, filing: Filing, data: ResponseInput, *, expected_version: int
) -> FilingResponse:
    code = data.response_type.code
    rule = RULES[code]
    status_change: SystemStatusChange | None = None
    with transaction.atomic():
        locked = lock_for_status_change(filing.application, expected_version)
        locked_filing = Filing.objects.select_for_update().get(pk=filing.pk)
        _ensure_latest_filing(locked, locked_filing)
        if data.received_at < locked_filing.filed_at:
            raise ValidationError(
                {"received_at": ["No puede ser anterior a la fecha de radicación."]}
            )
        corrected = None
        if data.corrects_response_id is not None:
            corrected = _ensure_correction(locked_filing, code, data.corrects_response_id)
        else:
            _ensure_status(locked, code)
        slots = _observed_slots(locked, data.observations) if data.observations else {}

        response = FilingResponse.objects.create(
            filing=locked_filing,
            response_type_item=data.response_type,
            reason_item=data.reason,
            received_at=data.received_at,
            external_reference=data.external_reference,
            public_message=data.public_message,
            internal_comment=data.internal_comment,
            approved_amount_cop=data.approved_amount_cop,
            approved_term_months=data.approved_term_months,
            valid_until=data.valid_until,
            disbursed_amount_cop=data.disbursed_amount_cop,
            recorded_by=actor,
            corrects_response=corrected,
        )
        if data.observations:
            _observe(actor, response, slots, data.observations)
        if corrected is None:
            if rule.target is not None and locked.status != rule.target:
                status_change = apply_system_transition(actor, locked, to_status=rule.target)
            if rule.filing_status is not None and locked_filing.status != rule.filing_status:
                locked_filing.status = rule.filing_status
                locked_filing.save(update_fields=["status", "updated_at"])
    logger.info("Respuesta %s registrada en la radicación %s por %s", code, filing.pk, actor.pk)
    if status_change is not None:
        notify_system_transition(actor, status_change)
    filing_response_recorded.send(
        sender=FilingResponse,
        response=response,
        filing=locked_filing,
        application=locked,
        status_changed=status_change is not None,
        actor=actor,
    )
    return response


def responses_visible_to(user: User) -> QuerySet[FilingResponse]:
    return responses_queryset().filter(
        filing__application__in=applications_visible_to(user).values("pk")
    )
