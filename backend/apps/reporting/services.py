"""Cálculos del dashboard (RF-70, RF-71, API §22.1). Todo sale de agregaciones en base
de datos (``Count``, ``Sum``, ``Avg`` y subconsultas): el número de consultas no crece
con las filas.

Embudo (cohorte): de las solicitudes **creadas** en el periodo, dentro del alcance y los
filtros, cuántas **llegaron alguna vez** a cada etapa según
``ApplicationStatusHistory.to_status``. Una solicitud cuenta una vez por etapa aunque
pase varias veces, y si llegó a una etapa posterior cuenta también en las anteriores
aunque el historial se las salte (el orden es el de ``FunnelStage``).

``DOCUMENTS_COMPLETE`` = llegó alguna vez a ``DOCUMENTS_REVIEW``. "Todos los obligatorios
aprobados o dispensados" en ese momento no se puede reconstruir del historial, así que
la etapa se aproxima con la entrada a revisión documental.

Montos (solo administrador y asesor), sobre la misma cohorte de solicitudes creadas en
el periodo:

- ``requested_total``: ``financing_preferences.requested_amount_cop``.
- ``approved_total``: ``filing_responses.approved_amount_cop`` de la respuesta
  ``APPROVED`` más reciente de cada solicitud.
- ``disbursed_total``: ``filing_responses.disbursed_amount_cop`` de la respuesta
  ``DISBURSED`` más reciente de cada solicitud.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import models
from django.db.models import (
    Avg,
    Count,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
)

from apps.applications.models import (
    TERMINAL_APPLICATION_STATUSES,
    ApplicationStatusHistory,
    CreditApplication,
)
from apps.applications.quick_filters import WAITING_STATUSES
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.services import CrmScope, clients_visible_to
from apps.filings import responses
from apps.filings.models import Filing, FilingResponse
from apps.identity.models import RoleCode, User
from apps.reporting.filters import ReportFilters, scoped_applications
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import DueWindow, due_condition

CONVERSION_QUANTUM = Decimal("0.0001")
DAYS_QUANTUM = Decimal("0.1")
SECONDS_PER_DAY = Decimal(86400)


class FunnelStage(models.TextChoices):
    """Etapas del embudo (RF-70), en orden."""

    CREATED = "CREATED", "Creadas"
    DOCUMENTS_COMPLETE = "DOCUMENTS_COMPLETE", "Documentos completos"
    READY_TO_FILE = "READY_TO_FILE", "Listas para radicar"
    FILED = "FILED", "Radicadas"
    APPROVED = "APPROVED", "Aprobadas"
    DISBURSED = "DISBURSED", "Desembolsadas"


# Estado del historial que marca la llegada a cada etapa (``CREATED`` no lo necesita:
# toda solicitud de la cohorte cuenta).
STAGE_STATUS: dict[str, str] = {
    FunnelStage.DOCUMENTS_COMPLETE: ApplicationStatus.DOCUMENTS_REVIEW,
    FunnelStage.READY_TO_FILE: ApplicationStatus.READY_TO_FILE,
    FunnelStage.FILED: ApplicationStatus.FILED,
    FunnelStage.APPROVED: ApplicationStatus.APPROVED,
    FunnelStage.DISBURSED: ApplicationStatus.DISBURSED,
}

OPEN_STATUSES: tuple[str, ...] = tuple(
    status for status in ApplicationStatus.values if status not in TERMINAL_APPLICATION_STATUSES
)


def ratio(count: int, base: int) -> Decimal | None:
    """``count / base`` con 4 decimales, o ``None`` si ``base`` es 0."""
    if base == 0:
        return None
    return (Decimal(count) / Decimal(base)).quantize(CONVERSION_QUANTUM, rounding=ROUND_HALF_UP)


def _reached_condition(stage: str) -> Q:
    """La solicitud llegó a ``stage`` o a una etapa posterior del embudo."""
    codes = list(FunnelStage.values)
    later = codes[codes.index(stage) :]
    statuses = [STAGE_STATUS[code] for code in later]
    history = ApplicationStatusHistory.objects.filter(
        application=OuterRef("pk"), to_status__in=statuses
    )
    return Q(Exists(history))


# --- Embudo -------------------------------------------------------------------------------


class FunnelGroupBy(models.TextChoices):
    """Desglose opcional de ``/reports/funnel`` (``group_by``)."""

    ADVISOR = "advisor", "Asesor"
    BANK = "bank", "Banco"
    PURPOSE = "purpose", "Finalidad"


@dataclass(frozen=True)
class Grouping:
    key: str
    # Campos que forman la etiqueta visible del grupo, unidos con un espacio.
    label_fields: tuple[str, ...]
    # Etiqueta de las solicitudes sin valor (por ejemplo, sin banco elegido).
    empty_label: str = ""


GROUPINGS: dict[str, Grouping] = {
    FunnelGroupBy.ADVISOR: Grouping(
        "assigned_advisor_id", ("assigned_advisor__first_name", "assigned_advisor__last_name")
    ),
    FunnelGroupBy.BANK: Grouping(
        "bank_product__bank_id", ("bank_product__bank__name",), empty_label="Sin banco"
    ),
    FunnelGroupBy.PURPOSE: Grouping("purpose_item__code", ("purpose_item__label",)),
}


def _stage_aggregates() -> dict[str, Count]:
    """Un ``Count`` por etapa, con el código de la etapa como alias."""
    aggregates: dict[str, Count] = {FunnelStage.CREATED.value: Count("pk")}
    for stage in STAGE_STATUS:
        aggregates[str(stage)] = Count("pk", filter=_reached_condition(stage))
    return aggregates


def funnel_stages(applications: QuerySet[CreditApplication]) -> list[dict[str, Any]]:
    """Etapas del embudo de la cohorte ``applications``, en una sola consulta."""
    return _stages_from_counts(applications.aggregate(**_stage_aggregates()))


def funnel_groups(applications: QuerySet[CreditApplication], group_by: str) -> list[dict[str, Any]]:
    """El embudo de cada grupo (asesor, banco o finalidad), en una sola consulta. Los
    grupos salen ordenados por etiqueta."""
    grouping = GROUPINGS[group_by]
    rows = (
        applications.order_by()
        .values(grouping.key, *grouping.label_fields)
        .annotate(**_stage_aggregates())
    )
    groups = []
    for row in rows:
        label = " ".join(str(row[name]) for name in grouping.label_fields if row[name])
        key = row[grouping.key]
        groups.append(
            {
                "key": None if key is None else str(key),
                "label": label or grouping.empty_label,
                "stages": _stages_from_counts(row),
            }
        )
    return sorted(groups, key=lambda group: (group["key"] is None, group["label"].lower()))


def _stages_from_counts(counts: dict[str, Any]) -> list[dict[str, Any]]:
    created = counts[FunnelStage.CREATED.value]
    stages: list[dict[str, Any]] = []
    previous: int | None = None
    for stage in FunnelStage:
        count = counts[stage.value]
        stages.append(
            {
                "code": stage.value,
                "count": count,
                "conversion": ratio(count, created),
                "step_conversion": None if previous is None else ratio(count, previous),
            }
        )
        previous = count
    return stages


def funnel(user: User, filters: ReportFilters, scope: CrmScope) -> dict[str, Any]:
    applications = scoped_applications(user, filters, scope=scope)
    return {"period": filters.period, "stages": funnel_stages(applications)}


def report_funnel(
    user: User, filters: ReportFilters, scope: CrmScope, group_by: str | None
) -> dict[str, Any]:
    """``/reports/funnel``: el embudo del dashboard y, con ``group_by``, el de cada grupo."""
    result = funnel(user, filters, scope)
    result["group_by"] = group_by
    result["groups"] = (
        funnel_groups(scoped_applications(user, filters, scope=scope), group_by) if group_by else []
    )
    return result


# --- Resumen ------------------------------------------------------------------------------


def _latest_response_amount(code: str, amount_field: str) -> Subquery:
    latest = (
        FilingResponse.objects.filter(
            filing__application=OuterRef("pk"),
            response_type_item__code=code,
            **{f"{amount_field}__isnull": False},
        )
        .order_by("-received_at", "-created_at")
        .values(amount_field)[:1]
    )
    return Subquery(latest, output_field=models.BigIntegerField())


def _money(value: int | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _status_snapshot(applications: QuerySet[CreditApplication]) -> list[dict[str, Any]]:
    by_status = dict(
        applications.order_by()
        .values("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    return [{"status": status, "count": by_status.get(status, 0)} for status in ApplicationStatus]


def _task_counts(user: User, filters: ReportFilters, scope: CrmScope) -> dict[str, int]:
    """Tareas `PENDING` vencidas y de hoy (RF-71): el administrador ve todas (o las del
    ``advisor_id``); el asesor, las asignadas a él. El broker no tiene tareas: 0 sin
    consultar."""
    if not (scope.sees_everything or scope.is_advisor):
        return {"overdue": 0, "due_today": 0}
    tasks = Task.objects.filter(status=TaskStatus.PENDING)
    if not scope.sees_everything:
        tasks = tasks.filter(assigned_to=user)
    elif filters.advisor_id is not None:
        tasks = tasks.filter(assigned_to_id=filters.advisor_id)
    return tasks.aggregate(
        overdue=Count("pk", filter=due_condition(DueWindow.OVERDUE)),
        due_today=Count("pk", filter=due_condition(DueWindow.TODAY)),
    )


def summary(user: User, filters: ReportFilters, scope: CrmScope) -> dict[str, Any]:
    """Indicadores del periodo. El broker no recibe ``amounts`` (la clave no existe)."""
    created = scoped_applications(user, filters, scope=scope)
    start, end = filters.datetime_range()
    sees_amounts = not scope.is_restricted
    if sees_amounts:
        totals = created.annotate(
            approved_amount=_latest_response_amount(responses.APPROVED, "approved_amount_cop"),
            disbursed_amount=_latest_response_amount(responses.DISBURSED, "disbursed_amount_cop"),
        ).aggregate(
            created=Count("pk"),
            requested=Sum("financing__requested_amount_cop"),
            approved=Sum("approved_amount"),
            disbursed=Sum("disbursed_amount"),
        )
    else:
        totals = created.aggregate(created=Count("pk"))

    result: dict[str, Any] = {
        "period": filters.period,
        "clients_created": clients_visible_to(user)
        .filter(created_at__gte=start, created_at__lt=end)
        .count(),
        "applications_created": totals["created"],
        "snapshot": _status_snapshot(
            scoped_applications(user, filters, scope=scope, by_creation_date=False)
        ),
        "tasks": _task_counts(user, filters, scope),
    }
    if sees_amounts:
        result["amounts"] = {
            "requested_total": _money(totals["requested"]),
            "approved_total": _money(totals["approved"]),
            "disbursed_total": _money(totals["disbursed"]),
        }
    return result


# --- Carga por asesor ---------------------------------------------------------------------


def _workload_advisors(
    user: User, filters: ReportFilters, scope: CrmScope, applications: QuerySet[Any]
) -> list[User]:
    """Filas de la carga: el asesor solo la suya; el administrador, la del ``advisor_id``
    o la de cada asesor activo más la de quien tenga solicitudes abiertas asignadas
    (aunque ya no sea asesor), para no perder carga."""
    if not scope.sees_everything:
        return [user]
    users = User.objects.all()
    if filters.advisor_id is not None:
        users = users.filter(pk=filters.advisor_id)
    else:
        active_advisor = Q(
            is_active=True,
            deleted_at__isnull=True,
            user_role_assignments__role__code=RoleCode.ADVISOR,
            user_role_assignments__role__is_active=True,
        )
        users = users.filter(
            active_advisor | Q(pk__in=applications.values("assigned_advisor_id"))
        ).distinct()
    return list(users.order_by("first_name", "last_name", "email"))


def workload(user: User, filters: ReportFilters, scope: CrmScope) -> dict[str, Any]:
    """Carga de hoy por asesor (el rango de fechas no aplica). Los conteos de solicitudes
    usan el alcance y los filtros; las tareas son las `PENDING` asignadas al asesor."""
    open_applications = scoped_applications(
        user, filters, scope=scope, by_creation_date=False
    ).filter(status__in=OPEN_STATUSES)
    advisors = _workload_advisors(user, filters, scope, open_applications)
    advisor_ids = [advisor.pk for advisor in advisors]

    application_counts: dict[Any, Mapping[str, Any]] = {
        row["assigned_advisor_id"]: row
        for row in open_applications.filter(assigned_advisor_id__in=advisor_ids)
        .order_by()
        .values("assigned_advisor_id")
        .annotate(
            open_applications=Count("pk"),
            waiting_buyer=Count("pk", filter=Q(status__in=WAITING_STATUSES)),
            ready_to_file=Count("pk", filter=Q(status=ApplicationStatus.READY_TO_FILE)),
        )
    }
    task_counts: dict[Any, Mapping[str, Any]] = {
        row["assigned_to_id"]: row
        for row in Task.objects.filter(status=TaskStatus.PENDING, assigned_to_id__in=advisor_ids)
        .order_by()
        .values("assigned_to_id")
        .annotate(
            overdue_tasks=Count("pk", filter=due_condition(DueWindow.OVERDUE)),
            due_today_tasks=Count("pk", filter=due_condition(DueWindow.TODAY)),
        )
    }
    rows = []
    for advisor in advisors:
        apps_row = application_counts.get(advisor.pk, {})
        tasks_row = task_counts.get(advisor.pk, {})
        rows.append(
            {
                "advisor_id": advisor.pk,
                "advisor_name": advisor.get_full_name(),
                "open_applications": apps_row.get("open_applications", 0),
                "overdue_tasks": tasks_row.get("overdue_tasks", 0),
                "due_today_tasks": tasks_row.get("due_today_tasks", 0),
                "waiting_buyer": apps_row.get("waiting_buyer", 0),
                "ready_to_file": apps_row.get("ready_to_file", 0),
            }
        )
    return {"advisors": rows}


# --- Resultados por banco -----------------------------------------------------------------


def _had_response(code: str) -> Q:
    return Q(
        Exists(FilingResponse.objects.filter(filing=OuterRef("pk"), response_type_item__code=code))
    )


def _days(duration: timedelta | None) -> Decimal | None:
    if duration is None:
        return None
    seconds = Decimal(duration.total_seconds())
    return (seconds / SECONDS_PER_DAY).quantize(DAYS_QUANTUM, rounding=ROUND_HALF_UP)


def bank_results(user: User, filters: ReportFilters, scope: CrmScope) -> dict[str, Any]:
    """Radicaciones del periodo (por ``filed_at``) agrupadas por el banco del producto
    radicado. Solo salen los bancos con al menos una radicación. Una radicación cuenta en
    ``returned``/``approved``/``rejected``/``disbursed`` si alguna vez recibió una
    respuesta de ese tipo; ``avg_days_to_response`` promedia los días entre ``filed_at``
    y la primera respuesta (las radicaciones sin respuesta no entran)."""
    start, end = filters.datetime_range()
    applications = scoped_applications(
        user, replace(filters, bank_id=None), scope=scope, by_creation_date=False
    )
    filings = Filing.objects.filter(
        application__in=applications.values("pk"), filed_at__gte=start, filed_at__lt=end
    )
    if filters.bank_id is not None:
        filings = filings.filter(bank_product__bank_id=filters.bank_id)
    first_response = (
        FilingResponse.objects.filter(filing=OuterRef("pk"))
        .order_by("received_at")
        .values("received_at")[:1]
    )
    time_to_response = ExpressionWrapper(
        Subquery(first_response, output_field=models.DateTimeField()) - F("filed_at"),
        output_field=DurationField(),
    )
    rows = (
        filings.order_by()
        .values("bank_product__bank_id", "bank_product__bank__name")
        .annotate(
            filings=Count("pk"),
            returned=Count("pk", filter=_had_response(responses.RETURNED)),
            approved=Count("pk", filter=_had_response(responses.APPROVED)),
            rejected=Count("pk", filter=_had_response(responses.REJECTED)),
            disbursed=Count("pk", filter=_had_response(responses.DISBURSED)),
            avg_time_to_response=Avg(time_to_response),
        )
        .order_by("bank_product__bank__name")
    )
    banks = [
        {
            "bank_id": row["bank_product__bank_id"],
            "bank_name": row["bank_product__bank__name"],
            "filings": row["filings"],
            "returned": row["returned"],
            "approved": row["approved"],
            "rejected": row["rejected"],
            "disbursed": row["disbursed"],
            "avg_days_to_response": _days(row["avg_time_to_response"]),
        }
        for row in rows
    ]
    return {"period": filters.period, "banks": banks}
