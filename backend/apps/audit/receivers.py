"""Suscriptores que llevan a la auditoría los eventos que ya tienen señal (Parte 2).

Se conectan en ``AuditConfig.ready``. ``record_audit`` nunca propaga un error. La
metadata lleva solo códigos, ids y estados: nunca los valores de datos personales.
"""

from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from apps.applications.models import CreditApplication
from apps.applications.signals import application_assigned, application_status_changed
from apps.audit.actions import AuditAction as A
from apps.audit.services import record_audit
from apps.banking.signals import (
    bank_policy_rule_status_changed,
    bank_product_status_changed,
    bank_status_changed,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions.models import CommissionSettlement, CommissionShare
from apps.commissions.signals import (
    commission_settled,
    commission_settlement_voided,
    commission_share_paid,
)
from apps.documents.models import ApplicationDocumentSlot, DocumentFile, DocumentReview
from apps.documents.models import ReviewDecision as D
from apps.documents.signals import (
    document_requirement_status_changed,
    document_reviewed,
    document_type_status_changed,
    document_uploaded,
)
from apps.filings.models import Filing, FilingResponse
from apps.filings.signals import filing_created, filing_response_recorded
from apps.identity.models import BuyerAccessLink, BuyerSession, ConsentAction, ConsentRecord, User
from apps.identity.signals import buyer_access_consumed, buyer_access_link_issued, consent_recorded
from apps.identity.users import user_status_changed

REVIEW_ACTIONS: dict[str, str] = {
    D.APPROVED: A.DOCUMENT_REVIEWED,
    D.REJECTED: A.DOCUMENT_REVIEWED,
    D.WAIVED: A.DOCUMENT_WAIVED,
    D.REOPENED: A.DOCUMENT_WAIVER_REOPENED,
}


# --- Autenticación ----------------------------------------------------------------------


@receiver(user_logged_in, dispatch_uid="audit.login")
def on_login(sender: Any, request: Any, user: User, **_: Any) -> None:
    record_audit(A.AUTH_LOGIN, user, actor=user, request=request)


@receiver(user_logged_out, dispatch_uid="audit.logout")
def on_logout(sender: Any, request: Any, user: User | None, **_: Any) -> None:
    record_audit(A.AUTH_LOGOUT, user if user is not None else "auth", actor=user, request=request)


# --- Comprador --------------------------------------------------------------------------


@receiver(buyer_access_link_issued, dispatch_uid="audit.buyer_link_created")
def on_link_issued(sender: Any, link: BuyerAccessLink, actor: User, **_: Any) -> None:
    channel = link.delivery_channel_item.code if link.delivery_channel_item else None
    record_audit(
        A.BUYER_LINK_CREATED,
        link,
        actor=actor,
        metadata={"application_id": str(link.application_id), "channel": channel},
    )


@receiver(buyer_access_consumed, dispatch_uid="audit.buyer_link_consumed")
def on_link_consumed(sender: Any, link: BuyerAccessLink, session: BuyerSession, **_: Any) -> None:
    record_audit(
        A.BUYER_LINK_CONSUMED,
        link,
        actor=session,
        metadata={"application_id": str(link.application_id), "session_id": str(session.pk)},
    )


@receiver(consent_recorded, dispatch_uid="audit.consent_recorded")
def on_consent_recorded(
    sender: Any, record: ConsentRecord, session: BuyerSession, **_: Any
) -> None:
    accepted = record.action == ConsentAction.ACCEPTED
    definition = record.consent_definition
    record_audit(
        A.CONSENT_ACCEPTED if accepted else A.CONSENT_WITHDRAWN,
        record,
        actor=session,
        metadata={
            "application_id": str(record.application_id),
            "consent_code": definition.code,
            "consent_version": definition.version,
        },
    )


# --- Archivos y expediente --------------------------------------------------------------


@receiver(document_uploaded, dispatch_uid="audit.document_uploaded")
def on_document_uploaded(
    sender: Any,
    slot: ApplicationDocumentSlot,
    document_file: DocumentFile,
    session: BuyerSession,
    **_: Any,
) -> None:
    record_audit(
        A.DOCUMENT_UPLOADED,
        document_file,
        actor=session,
        metadata={
            "application_id": str(slot.application_id),
            "slot_id": str(slot.pk),
            "document_type": slot.document_type.code,
            "version_number": document_file.version_number,
        },
    )


@receiver(document_reviewed, dispatch_uid="audit.document_reviewed")
def on_document_reviewed(
    sender: Any, slot: ApplicationDocumentSlot, review: DocumentReview, actor: User, **_: Any
) -> None:
    record_audit(
        REVIEW_ACTIONS[review.decision],
        slot,
        actor=actor,
        metadata={
            "application_id": str(slot.application_id),
            "decision": review.decision,
            "review_id": str(review.pk),
            "document_file_id": str(review.document_file_id) if review.document_file_id else None,
        },
    )


@receiver(application_status_changed, dispatch_uid="audit.application_status_changed")
def on_status_changed(
    sender: Any,
    application: CreditApplication,
    from_status: str,
    to_status: str,
    transition_code: str,
    reason_code: str | None,
    actor: Any,
    **_: Any,
) -> None:
    withdrawn = to_status == ApplicationStatus.WITHDRAWN
    record_audit(
        A.APPLICATION_WITHDRAWN if withdrawn else A.APPLICATION_STATUS_CHANGED,
        application,
        actor=actor,
        metadata={
            "from_status": from_status,
            "to_status": to_status,
            "transition_code": transition_code,
            "reason_code": reason_code,
        },
    )


@receiver(application_assigned, dispatch_uid="audit.application_assigned")
def on_assigned(
    sender: Any,
    application: CreditApplication,
    previous_advisor_id: Any,
    advisor_id: Any,
    actor: User,
    **_: Any,
) -> None:
    record_audit(
        A.APPLICATION_ASSIGNED,
        application,
        actor=actor,
        metadata={
            "previous_advisor_id": str(previous_advisor_id) if previous_advisor_id else None,
            "advisor_id": str(advisor_id),
        },
    )


# --- Radicación -------------------------------------------------------------------------


@receiver(filing_created, dispatch_uid="audit.filing_created")
def on_filing_created(
    sender: Any, filing: Filing, application: CreditApplication, actor: User, **_: Any
) -> None:
    record_audit(
        A.FILING_CREATED,
        filing,
        actor=actor,
        metadata={
            "application_id": str(application.pk),
            "sequence_number": filing.sequence_number,
            "bank_product_id": str(filing.bank_product_id),
        },
    )


@receiver(filing_response_recorded, dispatch_uid="audit.bank_response_recorded")
def on_response_recorded(
    sender: Any,
    response: FilingResponse,
    filing: Filing,
    application: CreditApplication,
    status_changed: bool,
    actor: User,
    **_: Any,
) -> None:
    record_audit(
        A.BANK_RESPONSE_RECORDED,
        response,
        actor=actor,
        metadata={
            "application_id": str(application.pk),
            "filing_id": str(filing.pk),
            "response_type": response.response_type_item.code,
            "corrects_response_id": (
                str(response.corrects_response_id) if response.corrects_response_id else None
            ),
            "status_changed": status_changed,
        },
    )


# --- Configuración ----------------------------------------------------------------------


def _status_change(action: str, resource: Any, **kwargs: Any) -> None:
    record_audit(
        action,
        resource,
        actor=kwargs.get("actor"),
        metadata={
            "from_status": kwargs.get("from_status"),
            "to_status": kwargs.get("to_status"),
            "reason": kwargs.get("reason") or "",
        },
    )


@receiver(bank_status_changed, dispatch_uid="audit.bank_status_changed")
def on_bank_status(sender: Any, bank: Any, **kwargs: Any) -> None:
    _status_change(A.BANK_CHANGED, bank, **kwargs)


@receiver(bank_product_status_changed, dispatch_uid="audit.bank_product_status_changed")
def on_product_status(sender: Any, product: Any, **kwargs: Any) -> None:
    _status_change(A.BANK_PRODUCT_CHANGED, product, **kwargs)


@receiver(bank_policy_rule_status_changed, dispatch_uid="audit.bank_rule_status_changed")
def on_rule_status(sender: Any, rule: Any, **kwargs: Any) -> None:
    _status_change(A.BANK_RULE_CHANGED, rule, **kwargs)


@receiver(document_requirement_status_changed, dispatch_uid="audit.requirement_status_changed")
def on_requirement_status(sender: Any, requirement: Any, **kwargs: Any) -> None:
    _status_change(A.DOCUMENT_REQUIREMENT_CHANGED, requirement, **kwargs)


@receiver(user_status_changed, dispatch_uid="audit.user_status_changed")
def on_user_status(sender: Any, user: User, **kwargs: Any) -> None:
    _status_change(A.USER_STATUS_CHANGED, user, **kwargs)


@receiver(document_type_status_changed, dispatch_uid="audit.document_type_status_changed")
def on_document_type_status(
    sender: Any, document_type: Any, is_active: bool, actor: User, reason: str = "", **_: Any
) -> None:
    record_audit(
        A.DOCUMENT_TYPE_CHANGED,
        document_type,
        actor=actor,
        metadata={"is_active": is_active, "reason": reason or ""},
    )


# --- Comisiones -------------------------------------------------------------------------
# Solo ids y códigos: nunca montos.


@receiver(commission_settled, dispatch_uid="audit.commission_settled")
def on_commission_settled(
    sender: Any, settlement: CommissionSettlement, actor: User | None, **_: Any
) -> None:
    record_audit(
        A.COMMISSION_SETTLED,
        settlement,
        actor=actor,
        metadata={
            "application_id": str(settlement.application_id),
            "plan_id": str(settlement.plan_id),
            "filing_response_id": str(settlement.filing_response_id),
            "lead_origin_code": settlement.lead_origin_code,
            "needs_review": settlement.needs_review,
        },
    )


@receiver(commission_settlement_voided, dispatch_uid="audit.commission_settlement_voided")
def on_commission_settlement_voided(
    sender: Any, settlement: CommissionSettlement, reason: str, actor: User | None, **_: Any
) -> None:
    record_audit(
        A.COMMISSION_SETTLEMENT_VOIDED,
        settlement,
        actor=actor,
        metadata={"application_id": str(settlement.application_id), "reason": reason},
    )


@receiver(commission_share_paid, dispatch_uid="audit.commission_share_paid")
def on_commission_share_paid(sender: Any, share: CommissionShare, actor: User, **_: Any) -> None:
    record_audit(
        A.COMMISSION_SHARE_PAID,
        share,
        actor=actor,
        metadata={
            "settlement_id": str(share.settlement_id),
            "beneficiary_role": share.beneficiary_role,
            "beneficiary_user_id": str(share.beneficiary_user_id),
        },
    )
