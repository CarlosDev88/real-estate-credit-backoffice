"""Suscriptores que crean las notificaciones del comprador (paso 13).

Las señales llegan después de confirmar la operación del dominio. Cada suscriptor crea
la notificación en su propia transacción (un ``savepoint`` si quien emite sigue dentro
de otra) y un error se registra en el log: nunca rompe la operación original.

| Tipo | Señal | ``deduplication_key`` |
| --- | --- | --- |
| ``ACCESS_GRANTED`` | ``buyer_access_consumed`` | ``<solicitud>:<cliente>`` (la primera vez) |
| ``DOCUMENT_REJECTED`` | ``document_reviewed`` con rechazo | ``<revisión>`` |
| ``READY_TO_FILE`` | ``application_status_changed`` | ``<solicitud>:<versión>`` |
| ``FILED`` | ``filing_created`` | ``<radicación>`` |
| ``BANK_*`` y ``DISBURSED`` | ``filing_response_recorded`` | ``<respuesta>`` |
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

from django.dispatch import receiver

from apps.applications.models import CreditApplication
from apps.applications.signals import application_status_changed
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.models import DocumentReview, ReviewDecision
from apps.documents.signals import document_reviewed
from apps.filings.models import Filing, FilingResponse
from apps.filings.signals import filing_created, filing_response_recorded
from apps.identity.buyer_portal import next_action
from apps.identity.models import BuyerAccessLink, BuyerSession
from apps.identity.signals import buyer_access_consumed
from apps.notifications import services
from apps.notifications.messages import long_date, pesos
from apps.notifications.models import NotificationType

logger = logging.getLogger(__name__)

# Tipo de respuesta del banco → notificación. `RECEIVED`, `IN_ANALYSIS` y `OTHER` no
# avisan al comprador; son además los únicos que admiten correcciones, así que una
# corrección nunca repite un aviso.
BANK_RESPONSE_TYPES: dict[str, str] = {
    "RETURNED": NotificationType.BANK_RETURNED,
    "APPROVED": NotificationType.BANK_APPROVED,
    "REJECTED": NotificationType.BANK_REJECTED,
    "DISBURSED": NotificationType.DISBURSED,
}

Handler = Callable[..., None]


def never_raises(handler: Handler) -> Handler:
    """Registra en el log cualquier error del suscriptor y no lo propaga."""

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            handler(*args, **kwargs)
        except Exception:
            logger.exception("No se pudo crear la notificación (%s)", handler.__name__)

    return wrapper


def _notify_primary(application: CreditApplication, notification_type: str, **values: Any) -> None:
    client = services.primary_client(application.pk)
    if client is None:
        logger.warning(
            "Solicitud %s sin titular activo: no se notifica %s",
            application.code,
            notification_type,
        )
        return
    services.notify_client(client, application, notification_type, **values)


@receiver(buyer_access_consumed, dispatch_uid="notifications.access_granted")
@never_raises
def on_buyer_access_consumed(
    sender: Any, link: BuyerAccessLink, session: BuyerSession, **kwargs: Any
) -> None:
    application = link.application
    services.notify_client(
        session.client,
        application,
        NotificationType.ACCESS_GRANTED,
        source_id=f"{application.pk}:{session.client_id}",
        next_action=next_action(application.status),
    )


@receiver(document_reviewed, dispatch_uid="notifications.document_rejected")
@never_raises
def on_document_reviewed(sender: Any, review: DocumentReview, **kwargs: Any) -> None:
    if review.decision != ReviewDecision.REJECTED:
        return
    slot = review.slot
    application = CreditApplication.objects.get(pk=slot.application_id)
    client = services.primary_client(application.pk)
    if client is None:
        return
    document = slot.document_type.name
    participant = slot.participant
    if participant is not None and participant.client_id != client.pk:
        document = f"{document} de {participant.client.full_name}"
    services.notify_client(
        client,
        application,
        NotificationType.DOCUMENT_REJECTED,
        source_id=review.pk,
        document=document,
        buyer_comment=review.buyer_comment or "",
    )


@receiver(application_status_changed, dispatch_uid="notifications.ready_to_file")
@never_raises
def on_application_status_changed(
    sender: Any, application: CreditApplication, to_status: str, **kwargs: Any
) -> None:
    if to_status != ApplicationStatus.READY_TO_FILE:
        return
    # La versión distingue cada vez que la solicitud vuelve a quedar lista.
    _notify_primary(
        application,
        NotificationType.READY_TO_FILE,
        source_id=f"{application.pk}:{application.version}",
    )


@receiver(filing_created, dispatch_uid="notifications.filed")
@never_raises
def on_filing_created(
    sender: Any, filing: Filing, application: CreditApplication, **kwargs: Any
) -> None:
    bank = filing.bank_product.bank
    _notify_primary(
        application,
        NotificationType.FILED,
        source_id=filing.pk,
        bank=bank.name,
        date=long_date(filing.filed_at),
    )


@receiver(filing_response_recorded, dispatch_uid="notifications.bank_response")
@never_raises
def on_filing_response_recorded(
    sender: Any, response: FilingResponse, application: CreditApplication, **kwargs: Any
) -> None:
    code = response.response_type_item.code
    notification_type = BANK_RESPONSE_TYPES.get(code)
    if notification_type is None:
        return
    if code == "DISBURSED" and response.corrects_response_id is not None:
        # Corregir el monto o la fecha del desembolso no es una novedad para el comprador.
        return
    approval = ""
    if response.approved_amount_cop is not None and response.approved_term_months is not None:
        amount = pesos(response.approved_amount_cop)
        approval = f"\n\nMonto aprobado: {amount} a {response.approved_term_months} meses."
    _notify_primary(
        application,
        notification_type,
        source_id=response.pk,
        public_message=response.public_message or "",
        approval=approval,
        date=long_date(response.received_at),
    )
