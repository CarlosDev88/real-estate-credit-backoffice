"""Revisión del expediente por el asesor (decisiones 7, 8 y 22; acordadas 6 y 8).

``PATCH /document-slots/{slot_id}/review`` con una de cuatro decisiones. Cada una deja
una fila nueva e inmutable en ``document_reviews`` por slot afectado: corregir una
decisión es otra fila, nunca se edita la anterior.

- ``APPROVED`` / ``REJECTED``: sobre ``document_file_id``, que debe ser la versión
  vigente del slot (``409 DOCUMENT_NOT_CURRENT``). Aprobar exige un análisis ``CLEAN``
  (``409 FILE_NOT_CLEAN``) y, si el slot tiene vigencia, una ``document_date`` que el
  asesor puede corregir; un documento vencido no se aprueba (``422
  DOCUMENT_EXPIRED``). La versión y el slot toman la decisión.
- ``WAIVED``: exonera el slot con un motivo del catálogo ``document_waiver_reason``. En
  un grupo alternativo exonera también los demás slots del grupo del mismo titular,
  salvo los ya aprobados (conservan su aprobación) o exonerados. Todos comparten un
  lote (``decision_batch_id``). Si alguno de los que se exonerarían no es exonerable,
  no se exonera ninguno.
- ``REOPENED``: deshace la última exoneración del slot y de los slots que se
  exoneraron en el mismo lote y siguen así. Cada slot vuelve al estado de su versión
  vigente (``PENDING`` si no tiene). Exige una nota interna.

Solo antes de `FILED` (``409 APPLICATION_NOT_EDITABLE``; terminada, ``409
APPLICATION_CLOSED``). Después de `FILED`, aprobar o rechazar se admite solo en un slot
con una observación abierta del banco (punto de enganche del paso 11). No cambia la
versión de la solicitud ni exige ``If-Match`` (acordada 6): bloquea las filas de los
slots, ordenadas por id.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.applications.exceptions import ApplicationClosed, ApplicationNotEditable
from apps.applications.models import CreditApplication
from apps.catalogs.models import CatalogItem
from apps.documents import uploads
from apps.documents.exceptions import (
    DocumentExpired,
    DocumentLocked,
    DocumentNotCurrent,
    FileNotClean,
)
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentFileStatus,
    DocumentReview,
    ReviewDecision,
    ScanStatus,
    SlotStatus,
)
from apps.documents.models.review import FILE_DECISIONS
from apps.identity.models import User
from config.exceptions import VALIDATION_MESSAGE, ApiError

logger = logging.getLogger(__name__)


class ReviewValidationError(ApiError):
    """``400 VALIDATION_ERROR`` que depende del estado del expediente, con el slot que
    lo provoca en ``details[].resource_id``."""

    error_code = "VALIDATION_ERROR"
    default_detail = VALIDATION_MESSAGE


@dataclass(frozen=True)
class Review:
    decision: str
    document_file_id: uuid.UUID | None = None
    reason_item: CatalogItem | None = None
    buyer_comment: str | None = None
    internal_comment: str | None = None
    document_date: date | None = None


def _detail(field: str, code: str, message: str, slot: ApplicationDocumentSlot) -> dict[str, str]:
    return {"field": field, "code": code, "message": message, "resource_id": str(slot.pk)}


def _lock_slots(slot_ids: Iterable[uuid.UUID]) -> list[ApplicationDocumentSlot]:
    """Bloquea los slots en orden de id (decisión 22). Solo las filas de los slots: las
    tablas relacionadas se leen sin bloquear."""
    return list(
        ApplicationDocumentSlot.objects.select_related(
            "document_type", "participant__client", "current_file__file_object"
        )
        .select_for_update(of=("self",))
        .filter(pk__in=set(slot_ids))
        .order_by("pk")
    )


def _ensure_reviewable(slot: ApplicationDocumentSlot, decision: str) -> None:
    application = CreditApplication.objects.only("status").get(pk=slot.application_id)
    if application.is_terminal:
        raise ApplicationClosed()
    if not application.is_editable:
        observed = decision in FILE_DECISIONS and uploads.slot_has_open_observation(slot)
        if not observed:
            raise ApplicationNotEditable(
                "El expediente solo se revisa antes de radicar, salvo los documentos "
                "observados por el banco."
            )
    if slot.retired_at is not None:
        raise DocumentLocked("El documento ya no aplica a la solicitud.")


def _holder(slot: ApplicationDocumentSlot) -> str:
    name = slot.document_type.name
    return f"«{name}» de {slot.participant.client.full_name}" if slot.participant else f"«{name}»"


def review_slot(actor: User, slot: ApplicationDocumentSlot, review: Review) -> list[uuid.UUID]:
    """Aplica la decisión y devuelve los ids de los slots que cambiaron."""
    if review.decision in FILE_DECISIONS:
        changed = [_decide_file(actor, slot.pk, review)]
    elif review.decision == ReviewDecision.WAIVED:
        changed = _waive(actor, slot, review)
    else:
        changed = _reopen(actor, slot, review)
    # Aprobar, rechazar, exonerar y reabrir pasan todos por aquí. Import local para no
    # crear un ciclo con `apps.applications.services`.
    from apps.applications.services import schedule_completeness_refresh

    schedule_completeness_refresh(slot.application_id)
    logger.info(
        "Revisión %s sobre %s slot(s) desde %s por %s",
        review.decision,
        len(changed),
        slot.pk,
        actor.pk,
    )
    return changed


# --- Aprobar y rechazar -----------------------------------------------------------------


def _approve(slot: ApplicationDocumentSlot, version: DocumentFile, review: Review) -> None:
    if version.file_object.scan_status != ScanStatus.CLEAN:
        raise FileNotClean()
    document_date = review.document_date or version.document_date
    if slot.validity_days is not None and document_date is None:
        raise ReviewValidationError(
            details=[
                _detail(
                    "document_date",
                    "REQUIRED",
                    "Este documento tiene vigencia: indica la fecha del documento.",
                    slot,
                )
            ]
        )
    expires_at = uploads.expires_on(slot, document_date)
    if expires_at is not None and expires_at <= timezone.localdate():
        raise DocumentExpired(
            details=[
                _detail(
                    "document_date",
                    "DOCUMENT_EXPIRED",
                    f"El documento venció el {expires_at.isoformat()}.",
                    slot,
                )
            ]
        )
    version.document_date = document_date
    version.expires_at = expires_at
    version.status = DocumentFileStatus.APPROVED


def _decide_file(actor: User, slot_id: uuid.UUID, review: Review) -> uuid.UUID:
    assert review.document_file_id is not None  # Lo exige el serializer.
    with transaction.atomic():
        (slot,) = _lock_slots([slot_id])
        _ensure_reviewable(slot, review.decision)
        if slot.status == SlotStatus.WAIVED:
            raise DocumentLocked(
                "El documento está exonerado: reabre la exoneración antes de revisar su archivo."
            )
        version = (
            DocumentFile.objects.select_related("file_object")
            .filter(slot=slot, pk=review.document_file_id)
            .first()
        )
        if version is None:
            raise ReviewValidationError(
                details=[
                    _detail(
                        "document_file_id",
                        "NOT_A_VERSION",
                        "El archivo no es una versión de este documento.",
                        slot,
                    )
                ]
            )
        if slot.current_file_id != version.pk:
            raise DocumentNotCurrent()

        if review.decision == ReviewDecision.APPROVED:
            _approve(slot, version, review)
            slot.status = SlotStatus.APPROVED
        else:
            version.status = DocumentFileStatus.REJECTED
            slot.status = SlotStatus.REJECTED
        version.save(update_fields=["status", "document_date", "expires_at"])
        slot.save(update_fields=["status", "updated_at"])
        DocumentReview.objects.create(
            slot=slot,
            document_file=version,
            reviewer=actor,
            decision=review.decision,
            reason_item=review.reason_item,
            buyer_comment=review.buyer_comment,
            internal_comment=review.internal_comment,
        )
    return slot.pk


# --- Exonerar ----------------------------------------------------------------------------


def _group_ids(slot: ApplicationDocumentSlot) -> set[uuid.UUID]:
    """El slot y, si está en un grupo alternativo, los slots vigentes del grupo del
    mismo titular (decisión 7)."""
    ids = {slot.pk}
    if slot.alternative_group_code:
        ids.update(
            ApplicationDocumentSlot.objects.filter(
                application_id=slot.application_id,
                participant_id=slot.participant_id,
                alternative_group_code=slot.alternative_group_code,
                retired_at__isnull=True,
            ).values_list("pk", flat=True)
        )
    return ids


def _in_group(candidate: ApplicationDocumentSlot, slot: ApplicationDocumentSlot) -> bool:
    if candidate.pk == slot.pk:
        return True
    return (
        candidate.retired_at is None
        and bool(slot.alternative_group_code)
        and candidate.alternative_group_code == slot.alternative_group_code
        and candidate.participant_id == slot.participant_id
    )


def _waive(actor: User, slot: ApplicationDocumentSlot, review: Review) -> list[uuid.UUID]:
    reason = review.reason_item
    assert reason is not None  # Lo exige el serializer.
    with transaction.atomic():
        locked = _lock_slots(_group_ids(slot))
        requested = next(candidate for candidate in locked if candidate.pk == slot.pk)
        _ensure_reviewable(requested, review.decision)
        members = [candidate for candidate in locked if _in_group(candidate, requested)]
        targets = [
            member
            for member in members
            if member.status not in (SlotStatus.APPROVED, SlotStatus.WAIVED)
        ]
        if not targets:
            raise ReviewValidationError(
                details=[
                    _detail(
                        "decision",
                        "NOTHING_TO_WAIVE",
                        "No hay documentos para exonerar: ya están aprobados o exonerados.",
                        requested,
                    )
                ]
            )
        blocked = [target for target in targets if not target.is_waivable]
        if blocked:
            raise ReviewValidationError(
                details=[
                    _detail(
                        "decision",
                        "NOT_WAIVABLE",
                        f"El documento {_holder(target)} no se puede exonerar.",
                        target,
                    )
                    for target in blocked
                ]
            )

        batch_id = uuid.uuid4()
        for target in targets:
            target.status = SlotStatus.WAIVED
            target.waiver_reason_item = reason
            target.save(update_fields=["status", "waiver_reason_item", "updated_at"])
        DocumentReview.objects.bulk_create(
            DocumentReview(
                slot=target,
                document_file_id=target.current_file_id,
                reviewer=actor,
                decision=ReviewDecision.WAIVED,
                reason_item=reason,
                internal_comment=review.internal_comment,
                decision_batch_id=batch_id,
            )
            for target in targets
        )
    return [target.pk for target in targets]


# --- Reabrir -----------------------------------------------------------------------------


def _waiver_batch(slot: ApplicationDocumentSlot) -> uuid.UUID | None:
    latest = (
        DocumentReview.objects.filter(slot=slot, decision=ReviewDecision.WAIVED)
        .order_by("-created_at")
        .values_list("decision_batch_id", flat=True)
        .first()
    )
    return latest


def _latest_reviews(slot_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, DocumentReview]:
    latest = (
        DocumentReview.objects.filter(slot_id__in=set(slot_ids))
        .order_by("slot_id", "-created_at")
        .distinct("slot_id")
    )
    return {review.slot_id: review for review in latest}


def restored_status(slot: ApplicationDocumentSlot) -> str:
    """Estado del slot según su versión vigente, al quitarle la exoneración."""
    version = slot.current_file
    if version is None:
        return SlotStatus.PENDING
    if version.status == DocumentFileStatus.APPROVED:
        return SlotStatus.APPROVED
    if version.status == DocumentFileStatus.REJECTED:
        return SlotStatus.REJECTED
    # `UPLOADED` (análisis en curso) o `IN_REVIEW` (espera al asesor).
    return SlotStatus.UPLOADED


def _reopen(actor: User, slot: ApplicationDocumentSlot, review: Review) -> list[uuid.UUID]:
    batch_id = _waiver_batch(slot)
    ids = {slot.pk}
    if batch_id is not None:
        ids.update(
            DocumentReview.objects.filter(
                decision=ReviewDecision.WAIVED, decision_batch_id=batch_id
            ).values_list("slot_id", flat=True)
        )
    with transaction.atomic():
        locked = _lock_slots(ids)
        requested = next(candidate for candidate in locked if candidate.pk == slot.pk)
        _ensure_reviewable(requested, review.decision)
        if requested.status != SlotStatus.WAIVED:
            raise ReviewValidationError(
                details=[
                    _detail(
                        "decision",
                        "NOT_WAIVED",
                        "Solo se reabre un documento exonerado.",
                        requested,
                    )
                ]
            )
        latest = _latest_reviews(candidate.pk for candidate in locked)

        def reopens(candidate: ApplicationDocumentSlot) -> bool:
            if candidate.pk == requested.pk:
                return True
            last = latest.get(candidate.pk)
            return (
                candidate.status == SlotStatus.WAIVED
                and candidate.retired_at is None
                and last is not None
                and last.decision == ReviewDecision.WAIVED
                and last.decision_batch_id == batch_id
            )

        targets = [candidate for candidate in locked if reopens(candidate)]
        reopen_batch = uuid.uuid4()
        for target in targets:
            target.status = restored_status(target)
            target.waiver_reason_item = None
            target.save(update_fields=["status", "waiver_reason_item", "updated_at"])
        DocumentReview.objects.bulk_create(
            DocumentReview(
                slot=target,
                document_file_id=target.current_file_id,
                reviewer=actor,
                decision=ReviewDecision.REOPENED,
                internal_comment=review.internal_comment,
                decision_batch_id=reopen_batch,
            )
            for target in targets
        )
    return [target.pk for target in targets]
