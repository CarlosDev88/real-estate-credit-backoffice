"""Suscriptores que llevan los eventos de los demás módulos a la actividad (API §21.1).

Se conectan en ``ActivityConfig.ready``. Cada uno corre en su propio punto de guardado y
nunca propaga un error: la operación que emitió la señal ya se confirmó, así que una
falla aquí solo se registra en el log (``never_raises``).

Al comprador (``BUYER``) solo van los cambios de estado con la etiqueta pública, sus
cargas, los rechazos con el mensaje para él y las respuestas del banco con
``public_message``. Nunca van notas, comentarios internos, identidades técnicas, IP ni
agente de usuario.
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

from django.db import transaction
from django.dispatch import receiver

from apps.activity.models import ActivityEventType as E
from apps.activity.models import ActivityVisibility as V
from apps.activity.services import record_activity
from apps.activity.texts import application_created_title, status_changed_title
from apps.applications.models import (
    ApplicationParticipant,
    ApplicationStatusHistory,
    CreditApplication,
)
from apps.applications.signals import (
    application_assigned,
    application_created,
    application_status_changed,
    participant_added,
    participant_removed,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentReview,
    ParticipantRole,
    ReviewDecision,
)
from apps.documents.signals import document_reviewed, document_uploaded
from apps.filings.models import Filing, FilingResponse
from apps.filings.signals import filing_created, filing_response_recorded
from apps.identity.buyer_portal import public_status_label
from apps.identity.models import BuyerAccessLink, BuyerSession, ConsentAction, ConsentRecord, User
from apps.identity.signals import buyer_access_consumed, buyer_access_link_issued, consent_recorded
from apps.tasks.models import Task
from apps.tasks.signals import task_cancelled, task_completed, task_created

logger = logging.getLogger(__name__)

Handler = Callable[..., None]

REVIEW_VERBS: dict[str, str] = {
    ReviewDecision.APPROVED: "aprobó",
    ReviewDecision.REJECTED: "rechazó",
    ReviewDecision.WAIVED: "exoneró",
    ReviewDecision.REOPENED: "reabrió la exoneración de",
}


def never_raises(handler: Handler) -> Handler:
    """Registra la actividad en un punto de guardado; un error queda en el log."""

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            with transaction.atomic():
                handler(*args, **kwargs)
        except Exception:
            logger.exception("No se pudo registrar la actividad de %s", handler.__name__)

    return wrapper


def document_label(slot: ApplicationDocumentSlot) -> str:
    """«Desprendible de nómina» 2 de 3, de Daniel Mejía (si no es del titular)."""
    label = f"«{slot.document_type.name}»"
    if slot.minimum_files > 1:
        label += f" {slot.slot_index} de {slot.minimum_files}"
    participant = slot.participant
    if participant is not None and participant.role != ParticipantRole.PRIMARY:
        label += f" de {participant.client.full_name}"
    return label


# --- Solicitud --------------------------------------------------------------------------


def _history_id(application: CreditApplication, **filters: Any) -> str | None:
    """La fila más reciente del historial de estados que corresponde al evento. El
    backfill la usa para no repetir lo que ya registró un suscriptor."""
    history_id = (
        ApplicationStatusHistory.objects.filter(application=application, **filters)
        .order_by("-created_at")
        .values_list("pk", flat=True)
        .first()
    )
    return str(history_id) if history_id else None


@receiver(application_created, dispatch_uid="activity.application_created")
@never_raises
def on_application_created(
    sender: Any, application: CreditApplication, actor: Any, **_: Any
) -> None:
    history_id = _history_id(application, from_status__isnull=True)
    record_activity(
        event_type=E.APPLICATION_CREATED,
        title=application_created_title(application.code),
        application=application,
        actor=actor,
        metadata={"status_history_id": history_id},
    )


@receiver(application_status_changed, dispatch_uid="activity.status_changed")
@never_raises
def on_status_changed(
    sender: Any,
    application: CreditApplication,
    from_status: str,
    to_status: str,
    transition_code: str,
    reason_code: str | None,
    comment: str,
    actor: Any,
    **_: Any,
) -> None:
    metadata = {
        "from_status": from_status,
        "to_status": to_status,
        "transition_code": transition_code,
        "reason_code": reason_code,
        "status_history_id": _history_id(application, to_status=to_status),
    }
    record_activity(
        event_type=E.STATUS_CHANGED,
        title=status_changed_title(
            ApplicationStatus(from_status).label, ApplicationStatus(to_status).label
        ),
        message=comment,
        application=application,
        actor=actor,
        metadata=metadata,
    )
    record_activity(
        event_type=E.STATUS_CHANGED,
        visibility=V.BUYER,
        title=status_changed_title(
            public_status_label(from_status), public_status_label(to_status)
        ),
        application=application,
        actor=actor,
        metadata={key: metadata[key] for key in ("from_status", "to_status", "status_history_id")},
    )


@receiver(application_assigned, dispatch_uid="activity.advisor_assigned")
@never_raises
def on_advisor_assigned(
    sender: Any, application: CreditApplication, advisor_id: Any, actor: Any, reason: str, **_: Any
) -> None:
    advisor = User.objects.get(pk=advisor_id)
    record_activity(
        event_type=E.ADVISOR_ASSIGNED,
        title=f"{advisor.get_full_name()} quedó como responsable",
        message=reason,
        application=application,
        actor=actor,
        metadata={"advisor_id": str(advisor_id)},
    )


def _participant_metadata(participant: ApplicationParticipant) -> dict[str, Any]:
    return {"participant_id": str(participant.pk), "role": participant.role}


@receiver(participant_added, dispatch_uid="activity.participant_added")
@never_raises
def on_participant_added(
    sender: Any,
    application: CreditApplication,
    participant: ApplicationParticipant,
    actor: Any,
    **_: Any,
) -> None:
    role = ParticipantRole(participant.role).label.lower()
    record_activity(
        event_type=E.PARTICIPANT_ADDED,
        title=f"Se agregó a {participant.client.full_name} como {role}",
        application=application,
        actor=actor,
        metadata=_participant_metadata(participant),
    )


@receiver(participant_removed, dispatch_uid="activity.participant_removed")
@never_raises
def on_participant_removed(
    sender: Any,
    application: CreditApplication,
    participant: ApplicationParticipant,
    actor: Any,
    **_: Any,
) -> None:
    role = ParticipantRole(participant.role).label.lower()
    record_activity(
        event_type=E.PARTICIPANT_REMOVED,
        title=f"Se retiró a {participant.client.full_name} como {role}",
        application=application,
        actor=actor,
        metadata=_participant_metadata(participant),
    )


# --- Documentos -------------------------------------------------------------------------


@receiver(document_uploaded, dispatch_uid="activity.document_uploaded")
@never_raises
def on_document_uploaded(
    sender: Any,
    slot: ApplicationDocumentSlot,
    document_file: DocumentFile,
    session: BuyerSession,
    **_: Any,
) -> None:
    title = f"{session.client.full_name} cargó {document_label(slot)}"
    metadata = {"slot_id": str(slot.pk), "document_file_id": str(document_file.pk)}
    for visibility in (V.INTERNAL, V.BUYER):
        record_activity(
            event_type=E.DOCUMENT_UPLOADED,
            visibility=visibility,
            title=title,
            application=slot.application,
            actor=session,
            metadata=metadata,
        )


@receiver(document_reviewed, dispatch_uid="activity.document_reviewed")
@never_raises
def on_document_reviewed(
    sender: Any,
    slot: ApplicationDocumentSlot,
    review: DocumentReview,
    actor: User,
    **_: Any,
) -> None:
    label = document_label(slot)
    metadata = {"slot_id": str(slot.pk), "review_id": str(review.pk), "decision": review.decision}
    record_activity(
        event_type=E.DOCUMENT_REVIEWED,
        title=f"{actor.get_full_name()} {REVIEW_VERBS[review.decision]} {label}",
        message=review.internal_comment or review.buyer_comment or "",
        application=slot.application,
        actor=actor,
        metadata=metadata,
    )
    if review.decision == ReviewDecision.REJECTED:
        record_activity(
            event_type=E.DOCUMENT_REVIEWED,
            visibility=V.BUYER,
            title=f"Tu asesor rechazó {label}",
            message=review.buyer_comment or "",
            application=slot.application,
            actor=actor,
            metadata=metadata,
        )


# --- Acceso del comprador y consentimientos ---------------------------------------------


@receiver(buyer_access_link_issued, dispatch_uid="activity.buyer_link_sent")
@never_raises
def on_buyer_link_issued(sender: Any, link: BuyerAccessLink, actor: User, **_: Any) -> None:
    record_activity(
        event_type=E.BUYER_LINK_SENT,
        title=f"{actor.get_full_name()} envió el enlace de acceso al comprador",
        application=link.application,
        actor=actor,
        metadata={
            "link_id": str(link.pk),
            "channel": link.delivery_channel_item.code if link.delivery_channel_item else None,
        },
    )


@receiver(buyer_access_consumed, dispatch_uid="activity.buyer_session_started")
@never_raises
def on_buyer_session_started(
    sender: Any, link: BuyerAccessLink, session: BuyerSession, **_: Any
) -> None:
    record_activity(
        event_type=E.BUYER_SESSION_STARTED,
        title="El comprador entró al portal",
        application=link.application,
        actor=session,
        metadata={"link_id": str(link.pk)},
    )


@receiver(consent_recorded, dispatch_uid="activity.consent_recorded")
@never_raises
def on_consent_recorded(
    sender: Any, record: ConsentRecord, session: BuyerSession, **_: Any
) -> None:
    verb = "aceptó" if record.action == ConsentAction.ACCEPTED else "retiró"
    definition = record.consent_definition
    record_activity(
        event_type=E.CONSENT_RECORDED,
        title=f"{session.client.full_name} {verb} «{definition.title}»",
        application=session.application,
        actor=session,
        metadata={
            "consent_code": definition.code,
            "consent_version": definition.version,
            "action": record.action,
        },
    )


# --- Tareas -----------------------------------------------------------------------------


def _record_task(event_type: str, prefix: str, task: Task, actor: User, message: str = "") -> None:
    record_activity(
        event_type=event_type,
        title=f"{prefix}: {task.title}",
        message=message,
        application=task.application,
        opportunity=task.opportunity,
        actor=actor,
        metadata={"task_id": str(task.pk)},
    )


@receiver(task_created, dispatch_uid="activity.task_created")
@never_raises
def on_task_created(sender: Any, task: Task, actor: User, **_: Any) -> None:
    _record_task(E.TASK_CREATED, "Tarea creada", task, actor)


@receiver(task_completed, dispatch_uid="activity.task_completed")
@never_raises
def on_task_completed(sender: Any, task: Task, actor: User, **_: Any) -> None:
    _record_task(E.TASK_COMPLETED, "Tarea completada", task, actor)


@receiver(task_cancelled, dispatch_uid="activity.task_cancelled")
@never_raises
def on_task_cancelled(sender: Any, task: Task, reason: str, actor: User, **_: Any) -> None:
    _record_task(E.TASK_CANCELLED, "Tarea cancelada", task, actor, message=reason)


# --- Radicación -------------------------------------------------------------------------


@receiver(filing_created, dispatch_uid="activity.filing_created")
@never_raises
def on_filing_created(
    sender: Any, filing: Filing, application: CreditApplication, actor: User, **_: Any
) -> None:
    bank = filing.bank_product.bank.name
    record_activity(
        event_type=E.FILING_CREATED,
        title=f"Radicada en {bank} (#{filing.sequence_number})",
        message=filing.comment or "",
        application=application,
        actor=actor,
        metadata={"filing_id": str(filing.pk), "sequence_number": filing.sequence_number},
    )


@receiver(filing_response_recorded, dispatch_uid="activity.bank_response_recorded")
@never_raises
def on_bank_response_recorded(
    sender: Any,
    response: FilingResponse,
    filing: Filing,
    application: CreditApplication,
    actor: User,
    **_: Any,
) -> None:
    bank = filing.bank_product.bank.name
    response_type = response.response_type_item
    metadata = {
        "filing_id": str(filing.pk),
        "response_id": str(response.pk),
        "response_type": response_type.code,
    }
    record_activity(
        event_type=E.BANK_RESPONSE_RECORDED,
        title=f"Respuesta de {bank}: {response_type.label}",
        message=response.internal_comment or response.public_message or "",
        application=application,
        actor=actor,
        metadata=metadata,
    )
    if response.public_message:
        record_activity(
            event_type=E.BANK_RESPONSE_RECORDED,
            visibility=V.BUYER,
            title=f"Respuesta de {bank}: {response_type.label}",
            message=response.public_message,
            application=application,
            actor=actor,
            metadata=metadata,
        )
