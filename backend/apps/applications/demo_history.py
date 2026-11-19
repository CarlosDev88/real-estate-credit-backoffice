"""Historia de seis meses de la demo (``seed_demo_data``, TAREA-brechas-3-demo, parte 2).

Unas 30 solicitudes más, repartidas en los últimos seis meses y en todos los estados del
flujo, para que el dashboard, el embudo por cohorte, "Mi día" y los reportes tengan
historia: cierres antes de radicar (cancelada, recursos propios, crédito externo y
desistida), radicadas sin respuesta (una vencida), recibidas, en análisis, devueltas,
devueltas y corregidas (segunda radicación), aprobadas, en legalización, rechazadas,
desembolsadas (de broker, 70/30, y directas, 100 %) y una desistida después de radicar.

Cada solicitud se construye con los servicios del dominio, igual que el resto de la demo
(``applications.demo_data``), con las fechas de radicación y de las respuestas ya en el
pasado. Después se **retroceden** sus fechas con ``update()`` (``backdate``): el historial
de estados recibe fechas reales (la creación, los pasos antes de radicar repartidos hasta
la radicación, y la fecha de cada respuesta del banco), y todo lo demás de la solicitud
(actividad, documentos, revisiones, paquetes, avisos, sesiones del comprador, liquidación)
se mueve con la fila del historial anterior más cercana, así que nada queda antes de lo
que lo causó: un desembolso nunca antes de su radicación.

La auditoría no se mueve: es inmutable (un trigger rechaza ``UPDATE``). Los eventos que
generan los servicios al sembrar quedan con la fecha de la siembra; los de la demo de
auditoría (``apps.audit.demo_data``) se insertan ya con su fecha.

Marca del bloque: los clientes de esta historia llevan un documento con
``HISTORY_DOCUMENT_PREFIX``; si alguno existe, el bloque no hace nada.
"""

import bisect
import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.activity.models import ActivityLog
from apps.applications import services
from apps.applications.demo_data import (
    ALL_DOCUMENTS,
    BANCOLOMBIA,
    BOGOTA,
    CO,
    EMPLOYEE,
    FNA,
    IMPROVEMENT,
    INDEPENDENT,
    MANY,
    NEW,
    PENSIONER,
    SOLIDARY,
    USED,
    DemoCase,
    _build_case,
    _fresh,
    _item,
    _Names,
    _open_buyer_session,
    _review,
    _transition,
    _upload,
)
from apps.applications.models import (
    ApplicationAssignment,
    ApplicationParticipant,
    ApplicationStatusHistory,
    BankRuleEvaluation,
    CreditApplication,
    FinancialProfile,
    FinancingPreference,
    IncomeSource,
    Property,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions.models import CommissionSettlement, CommissionShare
from apps.crm.models import Client, ClientAddress, Opportunity, OpportunityAssignment
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentFile,
    DocumentPackageJob,
    DocumentReview,
    FileObject,
    ReviewDecision,
)
from apps.documents.uploads import buyer_slots
from apps.filings import responses
from apps.filings.models import (
    Filing,
    FilingDocumentSnapshot,
    FilingResponse,
    FilingResponseObservation,
)
from apps.filings.services import create_filing
from apps.identity.models import BuyerAccessLink, BuyerSession, ConsentRecord, User
from apps.notifications.models import Notification, NotificationDelivery
from apps.partners.models import Project
from apps.tasks.models import Task

logger = logging.getLogger(__name__)

# Marca de los clientes de la historia (los de la demo base empiezan por 9900).
HISTORY_DOCUMENT_PREFIX = "9901"
# El último evento de una solicitud de la historia queda, como mínimo, este tiempo antes
# de ahora (para que nada caiga en el futuro por los segundos que tarda la siembra).
LATEST_EVENT_MARGIN = timedelta(hours=6)

S = ApplicationStatus
RF, R, WB, WD, D = (
    S.READY_TO_FILE,
    S.DOCUMENTS_REVIEW,
    S.WAITING_BUYER_DATA,
    S.WAITING_DOCUMENTS,
    S.DRAFT,
)
# Flujos.
PRE = "pre"  # Se queda en un estado antes de radicar.
CLOSE = "close"  # Se cierra antes de radicar (cancelada, recursos propios, externo).
WITHDRAW = "withdraw"  # Desiste (antes o después de radicar).
FILE = "file"  # Se radica y recibe respuestas.
# Pasos especiales dentro de ``responses`` de un caso radicado.
LEGALIZE = "LEGALIZE"  # Transición manual `APPROVED → LEGALIZATION`.
REFILE = "REFILE"  # Corrige lo observado y radica otra vez (segunda radicación).


@dataclass(frozen=True)
class HistoryCase:
    case: DemoCase
    # Días antes de hoy en que se creó la solicitud.
    days_ago: int
    flow: str = PRE
    # Días entre la creación y la radicación (o el cierre).
    days_to_file: int = 10
    # Respuestas del banco en orden (con ``LEGALIZE`` y ``REFILE``) y días entre cada una.
    responses: tuple[str, ...] = ()
    gap_days: int = 4
    # Cierre: estado y motivo; desistimiento: motivo.
    close_to: str = ""
    reason: str = ""
    # La oportunidad nace en el proyecto activo de la constructora de demo.
    with_project: bool = False
    # Desiste al final (después de las respuestas).
    withdraw_after: bool = False


def _filed(
    days_ago: int,
    responses_: tuple[str, ...],
    *,
    origin: str = "DIRECT",
    purpose: str = NEW,
    employment: str = EMPLOYEE,
    extra_role: str | None = None,
    days_to_file: int = 12,
    gap_days: int = 4,
    with_project: bool = False,
    withdraw_after: bool = False,
    reason: str = "",
) -> HistoryCase:
    return HistoryCase(
        DemoCase(
            RF,
            purpose,
            BANCOLOMBIA,
            employment,
            extra_role=extra_role,
            origin=origin,
            documents=ALL_DOCUMENTS,
            approve=MANY,
        ),
        days_ago=days_ago,
        flow=WITHDRAW if withdraw_after else FILE,
        days_to_file=days_to_file,
        responses=responses_,
        gap_days=gap_days,
        with_project=with_project,
        withdraw_after=withdraw_after,
        reason=reason,
    )


RECEIVED, IN_ANALYSIS, RETURNED, APPROVED, REJECTED, DISBURSED = (
    responses.RECEIVED,
    responses.IN_ANALYSIS,
    responses.RETURNED,
    responses.APPROVED,
    responses.REJECTED,
    responses.DISBURSED,
)
TO_DISBURSED = (RECEIVED, IN_ANALYSIS, APPROVED, LEGALIZE, DISBURSED)

HISTORY_CASES: tuple[HistoryCase, ...] = (
    # --- Hace 5 a 6 meses: casi todo cerrado -------------------------------------------
    _filed(178, TO_DISBURSED, origin="BROKER", gap_days=6),
    _filed(172, TO_DISBURSED, purpose=USED, employment=INDEPENDENT, gap_days=6),
    _filed(165, (RECEIVED, IN_ANALYSIS, REJECTED), employment=PENSIONER, purpose=IMPROVEMENT),
    HistoryCase(
        DemoCase(WD, USED, BANCOLOMBIA, EMPLOYEE),
        days_ago=160,
        flow=CLOSE,
        close_to=S.CANCELLED,
        reason="CLIENT_UNREACHABLE",
    ),
    _filed(155, TO_DISBURSED, origin="BROKER", extra_role=CO, with_project=True, gap_days=7),
    # --- Hace 4 a 5 meses ----------------------------------------------------------------
    HistoryCase(
        DemoCase(WB, NEW, BANCOLOMBIA, EMPLOYEE),
        days_ago=140,
        flow=CLOSE,
        days_to_file=8,
        close_to=S.OWN_FUNDS,
        reason="SOLD_OTHER_PROPERTY",
    ),
    _filed(135, TO_DISBURSED, with_project=True, gap_days=6),
    _filed(130, (RECEIVED, IN_ANALYSIS, REJECTED), origin="BROKER", employment=INDEPENDENT),
    HistoryCase(
        DemoCase(R, USED, BANCOLOMBIA, INDEPENDENT, documents=ALL_DOCUMENTS),
        days_ago=125,
        flow=WITHDRAW,
        days_to_file=9,
        reason="OTHER_FINANCING",
    ),
    _filed(120, TO_DISBURSED, origin="BROKER", purpose=USED, gap_days=6),
    # --- Hace 3 a 4 meses ----------------------------------------------------------------
    HistoryCase(
        DemoCase(WD, NEW, BANCOLOMBIA, EMPLOYEE, origin="REFERRAL"),
        days_ago=110,
        flow=CLOSE,
        close_to=S.EXTERNAL_CREDIT_APPROVED,
        reason="BETTER_RATE_ELSEWHERE",
    ),
    _filed(
        104,
        (RECEIVED, IN_ANALYSIS, RETURNED, REFILE, RECEIVED, IN_ANALYSIS, APPROVED, LEGALIZE),
        extra_role=SOLIDARY,
        gap_days=5,
    ),
    _filed(98, TO_DISBURSED, employment=PENSIONER, purpose=IMPROVEMENT, gap_days=6),
    _filed(
        92,
        (RECEIVED, IN_ANALYSIS),
        origin="BROKER",
        withdraw_after=True,
        reason="PROPERTY_CHANGED",
    ),
    HistoryCase(DemoCase(D, USED, FNA, INDEPENDENT), days_ago=88),
    # --- Hace 2 a 3 meses ----------------------------------------------------------------
    _filed(80, (RECEIVED, IN_ANALYSIS, APPROVED, LEGALIZE), with_project=True),
    _filed(75, (RECEIVED, IN_ANALYSIS, REJECTED), purpose=USED),
    HistoryCase(
        DemoCase(WD, IMPROVEMENT, BOGOTA, PENSIONER),
        days_ago=70,
        flow=CLOSE,
        close_to=S.CANCELLED,
        reason="CLIENT_DECLINED_PURCHASE",
    ),
    _filed(66, (RECEIVED, IN_ANALYSIS, APPROVED), origin="BROKER", extra_role=CO),
    _filed(62, (RECEIVED, RETURNED, REFILE, RECEIVED, IN_ANALYSIS), employment=INDEPENDENT),
    # --- Hace 1 a 2 meses ----------------------------------------------------------------
    _filed(52, (), days_to_file=12),  # Radicada sin respuesta y ya vencida.
    _filed(48, (RECEIVED, IN_ANALYSIS, APPROVED), purpose=USED, with_project=True),
    HistoryCase(DemoCase(WB, NEW, BANCOLOMBIA, None, origin="BROKER"), days_ago=45, flow=PRE),
    _filed(42, (RECEIVED, RETURNED), origin="BROKER", employment=PENSIONER, purpose=IMPROVEMENT),
    _filed(38, (RECEIVED, IN_ANALYSIS), employment=INDEPENDENT),
    # --- Último mes ----------------------------------------------------------------------
    _filed(26, (RECEIVED,), days_to_file=14, with_project=True),
    _filed(22, (RECEIVED, IN_ANALYSIS), origin="BROKER", days_to_file=10, gap_days=3),
    HistoryCase(
        DemoCase(R, NEW, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=2),
        days_ago=18,
    ),
    _filed(15, (), days_to_file=9),  # Radicada hace pocos días: todavía en plazo.
    HistoryCase(
        DemoCase(RF, USED, BANCOLOMBIA, EMPLOYEE, documents=ALL_DOCUMENTS, approve=MANY),
        days_ago=9,
    ),
)


@dataclass
class HistoryResult:
    applications: list[CreditApplication] = field(default_factory=list)


def history_exists() -> bool:
    return Client.objects.filter(document_number__startswith=HISTORY_DOCUMENT_PREFIX).exists()


class _HistoryNames(_Names):
    """Mismos nombres que la demo base, con el prefijo de la historia en el documento y un
    número propio en el correo. Empieza más adelante en la lista para no repetir los
    nombres de la demo base."""

    def __init__(self) -> None:
        super().__init__()
        self.number = 40

    def next(self) -> dict[str, Any]:
        data = super().next()
        data["document_number"] = f"{HISTORY_DOCUMENT_PREFIX}{self.number:06d}"
        data["email"] = data["email"].replace("@", ".h@", 1)
        data["phone"] = f"+57302555{self.number:04d}"
        return data


# --------------------------------------------------------------------------------------
# Construcción
# --------------------------------------------------------------------------------------


def _plan_times(history: HistoryCase, now: datetime) -> tuple[datetime, datetime, list[datetime]]:
    """Creación, radicación (o cierre) y fecha de cada paso posterior, todas en el pasado.

    Si los pasos no caben antes de ``now - LATEST_EVENT_MARGIN``, se comprime la separación.
    """
    start = now - timedelta(days=history.days_ago)
    latest = now - LATEST_EVENT_MARGIN
    filed_at = min(start + timedelta(days=history.days_to_file), latest - timedelta(hours=1))
    steps = len(history.responses) + (1 if history.withdraw_after else 0)
    gap = timedelta(days=history.gap_days)
    if steps and filed_at + gap * steps > latest:
        gap = (latest - filed_at) / (steps + 1)
    moments = [filed_at + gap * (index + 1) for index in range(steps)]
    return start, filed_at, moments


def _set_closing_financing(advisor: User, application: CreditApplication, mode: str) -> None:
    """El comprador cambia de modalidad: sin producto y sin monto solicitado."""
    current = FinancingPreference.objects.get(application=application)
    services.put_financing(
        advisor,
        application,
        expected_version=_fresh(application).version,
        values={
            "financing_mode_item": _item("financing_mode", mode),
            "requested_amount_cop": 0,
            "term_months": current.term_months,
            "currency_mode_item": current.currency_mode_item,
            "amortization_mode_item": current.amortization_mode_item,
            "own_resources_cop": current.own_resources_cop,
            "uses_severance_funds": current.uses_severance_funds,
            "severance_funds_cop": current.severance_funds_cop,
            "external_approved_amount_cop": (
                current.requested_amount_cop if mode == "EXTERNAL_CREDIT" else None
            ),
        },
        product=None,
    )


def _close(advisor: User, application: CreditApplication, history: HistoryCase) -> None:
    if history.close_to == S.OWN_FUNDS:
        _set_closing_financing(advisor, application, "OWN_FUNDS")
    elif history.close_to == S.EXTERNAL_CREDIT_APPROVED:
        _set_closing_financing(advisor, application, "EXTERNAL_CREDIT")
    services.transition_application(
        advisor,
        _fresh(application),
        to_status=history.close_to,
        expected_version=_fresh(application).version,
        reason=_item("application_transition_reason", history.reason),
        comment="Cierre de demo.",
    )


def _withdraw(advisor: User, application: CreditApplication, reason: str) -> None:
    services.withdraw_application(
        advisor,
        _fresh(application),
        expected_version=_fresh(application).version,
        reason=_item("application_withdrawal_reason", reason),
        comment="El comprador avisó por teléfono.",
    )


def _response(code: str, application: CreditApplication, at: datetime) -> Any:
    # Import local: `filings.demo_data` importa este paquete.
    from apps.filings.demo_data import _response_input

    return _response_input(code, application, at)


def _file(advisor: User, application: CreditApplication, *, filed_at: datetime) -> Filing:
    from apps.filings.demo_data import _completed_package

    job = _completed_package(advisor, application)
    sequence = Filing.objects.filter(application=application).count() + 1
    return create_filing(
        advisor,
        application,
        bank_product_id=application.bank_product_id,  # type: ignore[arg-type]
        package_job_id=job.pk,
        channel=_item("filing_channel", "BANK_PORTAL" if sequence == 1 else "EMAIL"),
        filed_at=filed_at,
        expected_version=_fresh(application).version,
        external_reference=f"DEMO-{application.code}-{sequence}",
        comment="Radicación de demo." if sequence == 1 else "Segunda radicación, ya corregida.",
    )


def _correct_observations(advisor: User, application: CreditApplication) -> None:
    """El comprador reemplaza lo observado por el banco y el asesor lo aprueba."""
    observed = list(
        FilingResponseObservation.objects.filter(
            document_slot__application=application, resolved_at__isnull=True
        ).values_list("document_slot_id", flat=True)
    )
    session = _open_buyer_session(advisor, _fresh(application))
    slots = buyer_slots(session).select_related("document_type")
    for position, slot_id in enumerate(observed):
        _upload(session, slots.get(pk=slot_id), position)
    for slot_id in observed:
        _review(advisor, slot_id, ReviewDecision.APPROVED)


def _respond(
    advisor: User, application: CreditApplication, history: HistoryCase, moments: list[datetime]
) -> None:
    filing = Filing.objects.filter(application=application).order_by("-sequence_number").first()
    assert filing is not None
    for code, at in zip(history.responses, moments, strict=False):
        if code == LEGALIZE:
            _transition(advisor, application, S.LEGALIZATION)
            continue
        if code == REFILE:
            _correct_observations(advisor, application)
            _transition(advisor, application, RF)
            filing = _file(advisor, _fresh(application), filed_at=at)
            continue
        if code == DISBURSED and _fresh(application).status == S.APPROVED:
            _transition(advisor, application, S.LEGALIZATION)
        responses.record_response(
            advisor,
            Filing.objects.get(pk=filing.pk),
            _response(code, application, at),
            expected_version=_fresh(application).version,
        )


def _build(
    history: HistoryCase,
    index: int,
    *,
    advisor: User,
    admin: User,
    broker: User,
    names: _Names,
    project: Project | None,
    now: datetime,
) -> CreditApplication:
    start, filed_at, moments = _plan_times(history, now)
    application = _build_case(
        history.case,
        index,
        advisor=advisor,
        admin=admin,
        broker=broker,
        names=names,
        project=project if history.with_project else None,
    )
    if history.flow == CLOSE:
        _close(advisor, application, history)
    elif history.flow == WITHDRAW and not history.responses:
        _withdraw(advisor, application, history.reason)
    elif history.flow in (FILE, WITHDRAW):
        _file(advisor, _fresh(application), filed_at=filed_at)
        _respond(advisor, application, history, moments)
        if history.withdraw_after:
            _withdraw(advisor, application, history.reason)
    application = _fresh(application)
    backdate(application, start=start, filed_at=filed_at, moments=moments, now=now)
    return _fresh(application)


def seed_history(
    *,
    advisors: list[User],
    admin: User,
    broker: User,
    project: Project | None,
    first_index: int,
) -> HistoryResult:
    """Crea la historia de seis meses. Quien llama comprueba ``history_exists``."""
    result = HistoryResult()
    names = _HistoryNames()
    assignments = _round_robin(advisors)
    now = timezone.now()
    for offset, history in enumerate(HISTORY_CASES):
        application = _build(
            history,
            first_index + offset,
            advisor=next(assignments),
            admin=admin,
            broker=broker,
            names=names,
            project=project,
            now=now,
        )
        result.applications.append(application)
    logger.info("Historia de demo: %s solicitudes", len(result.applications))
    return result


def _round_robin(advisors: list[User]) -> Iterator[User]:
    while True:
        yield from advisors


# --------------------------------------------------------------------------------------
# Fechas hacia atrás
# --------------------------------------------------------------------------------------


class _Clock:
    """Lleva un momento real de la siembra a su fecha de demo.

    Las anclas son las filas del historial de estados: (momento real, fecha de demo). Un
    momento real cae en la última ancla anterior y conserva su distancia a ella (segundos),
    así que el orden real se respeta y nada queda antes de lo que lo causó.
    """

    def __init__(self, anchors: list[tuple[datetime, datetime]]) -> None:
        self.real = [real for real, _ in anchors]
        self.demo = [demo for _, demo in anchors]

    def __call__(self, moment: datetime) -> datetime:
        position = bisect.bisect_right(self.real, moment) - 1
        if position < 0:
            return self.demo[0] - (self.real[0] - moment)
        return self.demo[position] + (moment - self.real[position])


def _history_dates(
    rows: list[ApplicationStatusHistory],
    *,
    start: datetime,
    filed_at: datetime,
    moments: list[datetime],
    explicit: dict[Any, datetime],
    now: datetime,
) -> list[datetime]:
    """Fecha de demo de cada fila del historial, en orden.

    La primera es la creación. Las que tienen fecha propia (radicaciones y respuestas del
    banco, en ``explicit``) la usan. Las demás se reparten entre la anterior y la
    siguiente con fecha conocida; sin siguiente, hasta la radicación planeada o, si ya
    pasó, hasta el último paso planeado.
    """
    known: list[datetime | None] = [None] * len(rows)
    known[0] = start
    for position, row in enumerate(rows):
        if row.pk in explicit:
            known[position] = explicit[row.pk]
    tail = max([filed_at, *moments]) if moments else filed_at
    ceiling = min(tail, now - LATEST_EVENT_MARGIN)
    result: list[datetime] = []
    position = 0
    while position < len(rows):
        value = known[position]
        if value is not None:
            result.append(value)
            position += 1
            continue
        previous = result[-1]
        following = next(
            (index for index in range(position, len(rows)) if known[index] is not None), None
        )
        end = known[following] if following is not None else max(ceiling, previous)
        assert end is not None
        count = (following if following is not None else len(rows)) - position
        step = (end - previous) / (count + 1)
        for offset in range(count):
            result.append(previous + step * (offset + 1))
        position += count
    return result


def _explicit_dates(application: CreditApplication, rows: list[ApplicationStatusHistory]) -> dict:
    """Filas del historial que corresponden a una radicación o a una respuesta del banco:
    la que se creó en la misma transacción (la más cercana en el tiempo real)."""
    events: list[tuple[datetime, datetime]] = []
    for filing in Filing.objects.filter(application=application):
        events.append((filing.created_at, filing.filed_at))
    for response in FilingResponse.objects.filter(filing__application=application):
        events.append((response.created_at, response.received_at))
    explicit: dict[Any, datetime] = {}
    for row in rows[1:]:
        if not events:
            break
        real, demo = min(events, key=lambda event: abs(event[0] - row.created_at))
        if abs(real - row.created_at) < timedelta(seconds=5) and row.to_status in (
            S.FILED,
            S.FILING_VALIDATION,
            S.CREDIT_ANALYSIS,
            S.BANK_OBSERVATION,
            S.APPROVED,
            S.REJECTED,
            S.DISBURSED,
        ):
            explicit[row.pk] = demo
    return explicit


def _shift(rows: Iterable[models.Model], fields: tuple[str, ...], clock: Callable) -> None:
    model: type[models.Model] | None = None
    for row in rows:
        model = type(row)
        changes = {
            name: clock(getattr(row, name)) for name in fields if getattr(row, name) is not None
        }
        if changes:
            model._default_manager.filter(pk=row.pk).update(**changes)


def backdate(
    application: CreditApplication,
    *,
    start: datetime,
    filed_at: datetime,
    moments: list[datetime],
    now: datetime,
) -> None:
    """Mueve al pasado todo lo de la solicitud. Ver el docstring del módulo."""
    rows = list(
        ApplicationStatusHistory.objects.filter(application=application).order_by(
            "created_at", "id"
        )
    )
    dates = _history_dates(
        rows,
        start=start,
        filed_at=filed_at,
        moments=moments,
        explicit=_explicit_dates(application, rows),
        now=now,
    )
    clock = _Clock([(row.created_at, date) for row, date in zip(rows, dates, strict=True)])
    for row, date in zip(rows, dates, strict=True):
        ApplicationStatusHistory.objects.filter(pk=row.pk).update(created_at=date)

    opportunity = Opportunity.objects.get(pk=application.opportunity_id)
    client_ids = list(
        ApplicationParticipant.objects.filter(application=application).values_list(
            "client_id", flat=True
        )
    )
    slots = ApplicationDocumentSlot.objects.filter(application=application)
    files = DocumentFile.objects.filter(slot__application=application)
    notifications = Notification.objects.filter(application=application)
    dt = ("created_at",)
    stamped = ("created_at", "updated_at")
    plan: list[tuple[Iterable[models.Model], tuple[str, ...]]] = [
        (
            CreditApplication.objects.filter(pk=application.pk),
            (
                "created_at",
                "updated_at",
                "current_stage_started_at",
                "ready_to_file_at",
                "withdrawn_at",
                "closed_at",
                "completeness_refreshed_at",
            ),
        ),
        (Client.objects.filter(pk__in=client_ids), stamped),
        (ClientAddress.objects.filter(client_id__in=client_ids), stamped),
        (Opportunity.objects.filter(pk=opportunity.pk), (*stamped, "converted_at")),
        (OpportunityAssignment.objects.filter(opportunity=opportunity), ("created_at", "ended_at")),
        (ApplicationAssignment.objects.filter(application=application), ("created_at", "ended_at")),
        (ApplicationParticipant.objects.filter(application=application), stamped),
        (
            FinancialProfile.objects.filter(participant__application=application),
            (*stamped, "data_confirmed_at"),
        ),
        (
            IncomeSource.objects.filter(financial_profile__participant__application=application),
            stamped,
        ),
        (Property.objects.filter(application=application), stamped),
        (FinancingPreference.objects.filter(application=application), stamped),
        (BankRuleEvaluation.objects.filter(application=application), dt),
        (slots, (*stamped, "locked_at", "retired_at")),
        (files, dt),
        (
            FileObject.objects.filter(pk__in=files.values("file_object_id")),
            ("created_at", "scanned_at"),
        ),
        (DocumentReview.objects.filter(slot__application=application), dt),
        (
            DocumentPackageJob.objects.filter(application=application),
            (*stamped, "started_at", "completed_at", "expires_at"),
        ),
        (Filing.objects.filter(application=application), stamped),
        (FilingDocumentSnapshot.objects.filter(filing__application=application), dt),
        (FilingResponse.objects.filter(filing__application=application), dt),
        (
            FilingResponseObservation.objects.filter(
                filing_response__filing__application=application
            ),
            ("created_at", "resolved_at"),
        ),
        (notifications, ("created_at", "read_at")),
        (
            NotificationDelivery.objects.filter(notification__in=notifications),
            (*stamped, "sent_at", "next_attempt_at"),
        ),
        (
            BuyerAccessLink.objects.filter(application=application),
            ("created_at", "expires_at", "consumed_at", "revoked_at"),
        ),
        (
            BuyerSession.objects.filter(application=application),
            ("created_at", "expires_at", "revoked_at", "last_seen_at"),
        ),
        (ConsentRecord.objects.filter(application=application), dt),
        (
            Task.objects.filter(application=application),
            (*stamped, "due_at", "completed_at", "cancelled_at"),
        ),
        (
            ActivityLog.objects.filter(
                Q(application=application)
                | Q(application__isnull=True, opportunity=opportunity)
                | Q(application__isnull=True, opportunity__isnull=True, client_id__in=client_ids)
            ),
            dt,
        ),
        (
            CommissionSettlement.objects.filter(application=application),
            (*stamped, "voided_at"),
        ),
        (CommissionShare.objects.filter(settlement__application=application), stamped),
    ]
    for queryset, fields in plan:
        _shift(list(queryset), fields, clock)
