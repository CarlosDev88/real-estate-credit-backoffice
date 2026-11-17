"""Consultas de "Mi día" (API §15.1).

Alcance: el asesor ve siempre sus solicitudes asignadas (``advisor_id`` se ignora); el
administrador ve todas, o las de ``advisor_id`` si lo envía. Solo entran las solicitudes
no terminales. Todo lo que muestra una fila sale de anotaciones, para que el número de
consultas no crezca con las filas.
"""

import uuid
from typing import Any

from django.db.models import (
    BooleanField,
    Count,
    ExpressionWrapper,
    Func,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.fields import DateField
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.applications.services import get_application_scope
from apps.identity.models import User
from apps.tasks.models import Task, TaskStatus
from apps.workday.rules import (
    WORKDAY_STATUSES,
    AttentionSegment,
    attention_field,
    segment_conditions,
)


def _pending_tasks_count() -> Coalesce:
    count = (
        Task.objects.filter(application=OuterRef("pk"), status=TaskStatus.PENDING)
        .order_by()
        .values("application")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return Coalesce(Subquery(count), 0)


def _days_in_stage() -> Func:
    """Días enteros desde el inicio de la etapa, con la fecha de Bogotá (``TIME_ZONE``):
    ``fecha de hoy - fecha de inicio``. En PostgreSQL, restar dos fechas da un entero."""
    today = Value(timezone.localdate(), output_field=DateField())
    started_on = TruncDate("current_stage_started_at", tzinfo=timezone.get_current_timezone())
    return Func(
        today,
        started_on,
        template="(%(expressions)s)",
        arg_joiner=" - ",
        output_field=IntegerField(),
    )


def workday_applications(actor: User, *, advisor_id: uuid.UUID | None = None) -> QuerySet[Any]:
    """Solicitudes de "Mi día" del actor, con los segmentos y los datos de la fila."""
    applications = CreditApplication.objects.filter(status__in=WORKDAY_STATUSES).select_related(
        "opportunity__client", "bank_product__bank"
    )
    if get_application_scope(actor).sees_everything:
        if advisor_id is not None:
            applications = applications.filter(assigned_advisor_id=advisor_id)
    else:
        applications = applications.filter(assigned_advisor=actor)

    segments = {
        attention_field(code): ExpressionWrapper(condition, output_field=BooleanField())
        for code, condition in segment_conditions(timezone.now()).items()
    }
    return applications.annotate(
        **segments,
        days_in_stage=_days_in_stage(),
        pending_tasks_count=_pending_tasks_count(),
    )


def filter_by_attention(applications: QuerySet[Any], code: str) -> QuerySet[Any]:
    return applications.filter(**{attention_field(code): True})


def summary(applications: QuerySet[Any]) -> dict[str, Any]:
    """``total`` y el conteo de cada segmento, en una sola consulta."""
    counts = applications.aggregate(
        total=Count("pk"),
        **{
            code: Count("pk", filter=Q(**{attention_field(code): True}))
            for code in AttentionSegment.values
        },
    )
    return {
        "total": counts["total"],
        "segments": [
            {"code": segment.value, "label": segment.label, "count": counts[segment.value]}
            for segment in AttentionSegment
        ],
    }
