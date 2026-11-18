"""Disparo automático de la liquidación: ``filing_response_recorded`` con una respuesta
`DISBURSED` (la solicitud pasa a `DISBURSED` en ese mismo registro).

La respuesta del banco ya quedó guardada, así que el receptor nunca propaga un error.
Sin plan vigente emite ``commission_plan_missing`` (la actividad lo muestra al
administrador, que crea el plan y liquida a mano) y deja un ``logger.warning`` solo con
ids. Cualquier otro error queda en el log.
"""

import logging
from typing import Any

from django.dispatch import receiver

from apps.applications.models import CreditApplication
from apps.commissions.exceptions import CommissionPlanNotFound
from apps.commissions.settlement import DISBURSED_RESPONSE, settle_application
from apps.commissions.signals import commission_plan_missing
from apps.filings.models import FilingResponse
from apps.filings.signals import filing_response_recorded

logger = logging.getLogger(__name__)


@receiver(filing_response_recorded, dispatch_uid="commissions.settle_on_disbursement")
def on_response_recorded(
    sender: Any,
    response: FilingResponse,
    application: CreditApplication,
    actor: Any,
    **_: Any,
) -> None:
    if response.response_type_item.code != DISBURSED_RESPONSE:
        return
    try:
        settle_application(application.pk, actor=actor, response=response)
    except CommissionPlanNotFound:
        logger.warning(
            "Sin plan de comisión vigente: solicitud %s, producto %s, respuesta %s",
            application.pk,
            response.filing.bank_product_id,
            response.pk,
        )
        commission_plan_missing.send(
            sender=FilingResponse, application=application, response=response, actor=actor
        )
    except Exception:
        logger.exception("No se pudo liquidar la comisión de la solicitud %s", application.pk)
