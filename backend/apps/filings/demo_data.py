"""Solicitudes radicadas de los datos de demo (``seed_demo_data``, paso 11).

Cuatro solicitudes que llegan a `READY_TO_FILE` igual que las demás de la demo
(``applications.demo_data``) y después pasan por los servicios de la radicación:

- una en `CREDIT_ANALYSIS` (recibida y en análisis);
- una en `BANK_OBSERVATION`, devuelta con un documento observado, que el comprador puede
  reemplazar desde el portal;
- una en `APPROVED`, con monto y plazo aprobados;
- una de broker en `DISBURSED`: aprobada, en legalización (transición manual del
  asesor) y desembolsada por el monto aprobado. Si comisiones tiene un plan vigente para
  el producto, su receptor la liquida (asesor y broker).

Cada una pide su paquete, lo arma y lo radica. Las fechas son de los últimos días, en
orden, y nunca futuras. La idempotencia es la del comando: si los datos de demo ya
existen, no se crea nada.
"""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from apps.applications.demo_data import (
    ALL_DOCUMENTS,
    BANCOLOMBIA,
    CO,
    EMPLOYEE,
    INDEPENDENT,
    MANY,
    NEW,
    RF,
    USED,
    DemoCase,
    _build_case,
    _fresh,
    _item,
    _Names,
)
from apps.applications.models import CreditApplication, FinancingPreference
from apps.applications.services import transition_application
from apps.catalogs.workflow import ApplicationStatus
from apps.documents.models import ApplicationDocumentSlot, DocumentPackageJob, PackageJobStatus
from apps.documents.packages import build_package, request_package
from apps.filings import responses
from apps.filings.models import Filing
from apps.filings.services import create_filing
from apps.identity.models import User

logger = logging.getLogger(__name__)

# Espera máxima del paquete si lo arma un worker (modo completo).
PACKAGE_WAIT_SECONDS = 60
FILED_DAYS_AGO = 6


@dataclass(frozen=True)
class FiledCase:
    case: DemoCase
    channel: str
    # Respuestas del banco, en orden, después de radicar.
    responses: tuple[str, ...]


FILED_DEMO_CASES: tuple[FiledCase, ...] = (
    FiledCase(
        DemoCase(RF, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=MANY),
        channel="BANK_PORTAL",
        responses=(responses.RECEIVED, responses.IN_ANALYSIS),
    ),
    FiledCase(
        DemoCase(RF, USED, BANCOLOMBIA, INDEPENDENT, documents=ALL_DOCUMENTS, approve=MANY),
        channel="EMAIL",
        responses=(responses.RECEIVED, responses.RETURNED),
    ),
    FiledCase(
        DemoCase(
            RF, NEW, BANCOLOMBIA, EMPLOYEE, extra_role=CO, documents=ALL_DOCUMENTS, approve=MANY
        ),
        channel="IN_PERSON",
        responses=(responses.RECEIVED, responses.IN_ANALYSIS, responses.APPROVED),
    ),
    FiledCase(
        DemoCase(
            RF,
            NEW,
            BANCOLOMBIA,
            EMPLOYEE,
            origin="BROKER",
            documents=ALL_DOCUMENTS,
            approve=MANY,
        ),
        channel="BANK_PORTAL",
        # Entre la aprobación y el desembolso, el asesor inicia la legalización.
        responses=(
            responses.RECEIVED,
            responses.IN_ANALYSIS,
            responses.APPROVED,
            responses.DISBURSED,
        ),
    ),
)
# El estado en que queda cada una, en el mismo orden.
FILED_DEMO_STATUSES = (
    ApplicationStatus.CREDIT_ANALYSIS,
    ApplicationStatus.BANK_OBSERVATION,
    ApplicationStatus.APPROVED,
    ApplicationStatus.DISBURSED,
)


def _completed_package(actor: User, application: CreditApplication) -> DocumentPackageJob:
    """Pide el paquete y lo arma aquí mismo. Con un worker (modo completo) puede ganarle
    el trabajo: entonces espera a que termine."""
    job = request_package(actor, application).job
    build_package(job.pk)
    deadline = time.monotonic() + PACKAGE_WAIT_SECONDS
    job.refresh_from_db()
    while job.status in (PackageJobStatus.PENDING, PackageJobStatus.RUNNING):
        if time.monotonic() > deadline:
            raise RuntimeError(f"El paquete {job.pk} no terminó a tiempo.")
        time.sleep(0.5)
        job.refresh_from_db()
    if job.status != PackageJobStatus.COMPLETED:
        raise RuntimeError(f"El paquete {job.pk} terminó en {job.status}.")
    return job


def _observed_slot(application: CreditApplication) -> ApplicationDocumentSlot:
    slot = (
        ApplicationDocumentSlot.objects.filter(
            application=application,
            retired_at__isnull=True,
            is_required=True,
            current_file__isnull=False,
        )
        .exclude(status="WAIVED")
        .order_by("sort_order", "slot_index", "pk")
        .first()
    )
    assert slot is not None
    return slot


def _response_input(
    code: str, application: CreditApplication, received_at: datetime
) -> responses.ResponseInput:
    response_type = _item(responses.RESPONSE_TYPE_CATALOG, code)
    if code == responses.RETURNED:
        slot = _observed_slot(application)
        return responses.ResponseInput(
            response_type=response_type,
            received_at=received_at,
            reason=_item("filing_return_reason", "DOCUMENT_CORRECTION"),
            public_message=(
                "El banco pide actualizar un documento. Cárgalo de nuevo desde el portal."
            ),
            internal_comment="Devolución de demo recibida por correo.",
            observations=[
                responses.Observation(
                    document_slot_id=slot.pk,
                    reason=_item("document_rejection_reason", "OUTDATED"),
                    message="Carga una versión expedida hace menos de 30 días.",
                )
            ],
        )
    if code == responses.APPROVED:
        financing = FinancingPreference.objects.get(application=application)
        return responses.ResponseInput(
            response_type=response_type,
            received_at=received_at,
            public_message="¡Tu crédito fue aprobado! Tu asesor te contará los siguientes pasos.",
            internal_comment="Aprobación de demo, sujeta a legalización.",
            approved_amount_cop=financing.requested_amount_cop,
            approved_term_months=financing.term_months,
            valid_until=(received_at + timedelta(days=90)).date(),
        )
    if code == responses.DISBURSED:
        financing = FinancingPreference.objects.get(application=application)
        return responses.ResponseInput(
            response_type=response_type,
            received_at=received_at,
            external_reference=f"DES-{application.code}",
            public_message="¡Tu crédito fue desembolsado! Felicitaciones por tu nueva vivienda.",
            internal_comment="Desembolso de demo.",
            disbursed_amount_cop=financing.requested_amount_cop,
        )
    public = "El banco recibió tu solicitud." if code == responses.RECEIVED else None
    return responses.ResponseInput(
        response_type=response_type, received_at=received_at, public_message=public
    )


def _file_and_respond(
    advisor: User, application: CreditApplication, filed: FiledCase, *, filed_at: datetime
) -> CreditApplication:
    job = _completed_package(advisor, application)
    filing = create_filing(
        advisor,
        application,
        bank_product_id=application.bank_product_id,  # type: ignore[arg-type]
        package_job_id=job.pk,
        channel=_item("filing_channel", filed.channel),
        filed_at=filed_at,
        expected_version=_fresh(application).version,
        external_reference=f"DEMO-{application.code}",
        comment="Radicación de demo.",
    )
    for day, code in enumerate(filed.responses, start=1):
        if code == responses.DISBURSED:
            transition_application(
                advisor,
                _fresh(application),
                to_status=ApplicationStatus.LEGALIZATION,
                expected_version=_fresh(application).version,
            )
        responses.record_response(
            advisor,
            Filing.objects.get(pk=filing.pk),
            _response_input(code, application, filed_at + timedelta(days=day)),
            expected_version=_fresh(application).version,
        )
    return _fresh(application)


def seed_filed_cases(
    *,
    assignments: Iterator[User],
    admin: User,
    broker: User,
    names: _Names,
    first_index: int,
) -> list[CreditApplication]:
    """Crea las cuatro solicitudes radicadas. ``assignments`` reparte los asesores como en
    el resto de la demo."""
    created = []
    filed_at = timezone.now() - timedelta(days=FILED_DAYS_AGO)
    for offset, filed in enumerate(FILED_DEMO_CASES):
        advisor = next(assignments)
        application = _build_case(
            filed.case,
            first_index + offset,
            advisor=advisor,
            admin=admin,
            broker=broker,
            names=names,
        )
        created.append(_file_and_respond(advisor, application, filed, filed_at=filed_at))
    logger.info("Solicitudes radicadas de demo: %s", len(created))
    return created
