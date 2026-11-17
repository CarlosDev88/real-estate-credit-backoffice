"""Fixtures del dashboard y los reportes.

Las pruebas viven en ``tests/reporting`` (no bajo ``tests/applications``), así que los
usuarios, clientes, oportunidades y solicitudes se importan de ``tests.applications``.
"""

from collections.abc import Callable
from datetime import date, datetime, time
from itertools import count
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import (
    ApplicationStatusHistory,
    CreditApplication,
    FinancingPreference,
    Property,
)
from apps.crm.models import Client, Opportunity
from apps.filings.models import Filing, FilingResponse
from apps.identity.models import User
from apps.partners.models import Project
from apps.tasks.models import Task, TaskStatus
from tests.applications.conftest import (
    admin_client,
    admin_user,
    advisor_client,
    advisor_user,
    broker_client,
    broker_user,
    catalog_item,
    make_application,
    make_client,
    make_opportunity,
    make_project,
    other_advisor,
    other_advisor_client,
    partner,
    partner_client,
)
from tests.applications.filings.conftest import make_filing

__all__ = [
    "admin_client",
    "admin_user",
    "advisor_client",
    "advisor_user",
    "broker_client",
    "broker_user",
    "make_application",
    "make_client",
    "make_filing",
    "make_opportunity",
    "make_project",
    "other_advisor",
    "other_advisor_client",
    "partner",
    "partner_client",
]

SUMMARY_URL = "/api/v1/dashboard/summary"
FUNNEL_URL = "/api/v1/dashboard/funnel"
WORKLOAD_URL = "/api/v1/dashboard/workload"
BANK_RESULTS_URL = "/api/v1/dashboard/bank-results"

_numbers = count(1)


def at(day: date, hour: int = 10) -> datetime:
    """Instante de ``day`` a ``hour`` en Bogotá."""
    return timezone.make_aware(datetime.combine(day, time(hour)))


def set_created_at(instance: Any, when: datetime) -> None:
    type(instance).objects.filter(pk=instance.pk).update(created_at=when)


def add_history(application: CreditApplication, *statuses: str) -> None:
    """Historial con los estados dados, en orden (el primero sin ``from_status``)."""
    previous: str | None = None
    for status in statuses:
        ApplicationStatusHistory.objects.create(
            application=application,
            from_status=previous,
            to_status=status,
            application_version=1,
        )
        previous = status


def add_financing(application: CreditApplication, amount: int) -> FinancingPreference:
    return FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "BANK_CREDIT"),
        requested_amount_cop=amount,
    )


def add_property(application: CreditApplication, project: Project | None) -> Property:
    return Property.objects.create(
        application=application,
        project=project,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        estimated_value_cop=420_000_000,
    )


def add_response(filing: Filing, code: str, received_at: datetime, **extra: Any) -> FilingResponse:
    return FilingResponse.objects.create(
        filing=filing,
        response_type_item=catalog_item("filing_response_type", code),
        received_at=received_at,
        recorded_by=filing.filed_by,
        **extra,
    )


@pytest.fixture
def make_report_application(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
    advisor_user: User,
) -> Callable[..., CreditApplication]:
    """Solicitud con su propio cliente y oportunidad, creada en ``created_at`` (por
    omisión, ahora)."""

    def _make(
        status: str = "DRAFT",
        advisor: User | None = None,
        created_at: datetime | None = None,
        origin_user: User | None = None,
        opportunity_project: Project | None = None,
        **extra: Any,
    ) -> CreditApplication:
        number = next(_numbers)
        client = make_client(document_number=f"8800{number:06d}")
        opportunity = make_opportunity(
            client,
            assigned_advisor=advisor or advisor_user,
            origin_user=origin_user,
            project=opportunity_project,
        )
        application = make_application(
            opportunity, status=status, assigned_advisor=advisor or advisor_user, **extra
        )
        if created_at is not None:
            set_created_at(application, created_at)
            application.refresh_from_db()
        return application

    return _make


@pytest.fixture
def make_task(advisor_user: User) -> Callable[..., Task]:
    def _make(application: CreditApplication, due_at: datetime | None, **extra: Any) -> Task:
        extra.setdefault("assigned_to", advisor_user)
        extra.setdefault("title", "Llamar al comprador")
        extra.setdefault("priority_item", catalog_item("task_priority", "MEDIUM"))
        extra.setdefault("status", TaskStatus.PENDING)
        return Task.objects.create(application=application, due_at=due_at, **extra)

    return _make
