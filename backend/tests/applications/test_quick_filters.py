"""Pestañas rápidas del listado (TAREA-applications-listado, Parte 4): configuración,
conteos con el alcance y los filtros del listado, y ``quick_filter``."""

from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.applications.quick_filters import QUICK_FILTERS
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import APPLICATIONS_URL, catalog_item
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

QUICK_FILTERS_URL = f"{APPLICATIONS_URL}/quick-filters"
ApplicationFactory = Callable[..., CreditApplication]


@pytest.fixture
def new_application(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: ApplicationFactory,
) -> ApplicationFactory:
    numbers = iter(range(1, 1000))

    def _new_application(
        status: str = ApplicationStatus.DRAFT, first_names: str = "Laura", **extra: Any
    ) -> CreditApplication:
        client = make_client(document_number=f"31{next(numbers):08}", first_names=first_names)
        application = make_application(make_opportunity(client), **extra)
        CreditApplication.objects.filter(pk=application.pk).update(status=status)
        return application

    return _new_application


def counts(client: APIClient, **params: Any) -> dict[str, int]:
    response = client.get(QUICK_FILTERS_URL, params)
    assert response.status_code == 200, response.content
    return {item["code"]: item["count"] for item in response.json()}


def list_codes(client: APIClient, **params: Any) -> set[str]:
    response = client.get(APPLICATIONS_URL, params)
    assert response.status_code == 200, response.content
    return {item["code"] for item in response.json()["items"]}


@pytest.fixture
def mixed(new_application: ApplicationFactory) -> dict[str, CreditApplication]:
    """Una solicitud por estado relevante, del asesor por omisión."""
    return {
        "draft_1": new_application(ApplicationStatus.DRAFT),
        "draft_2": new_application(ApplicationStatus.DRAFT),
        "buyer_data": new_application(ApplicationStatus.WAITING_BUYER_DATA),
        "documents": new_application(ApplicationStatus.WAITING_DOCUMENTS),
        "review": new_application(ApplicationStatus.DOCUMENTS_REVIEW),
        "ready": new_application(ApplicationStatus.READY_TO_FILE),
        "filed": new_application(ApplicationStatus.FILED),
        "rejected": new_application(ApplicationStatus.REJECTED),
    }


EXPECTED = {
    "all": 8,
    "draft": 2,
    "waiting": 2,
    "review": 1,
    "ready": 1,
    "bank": 1,
    "closed": 1,
}


# --- Configuración ------------------------------------------------------------------------


def test_every_status_is_in_exactly_one_tab() -> None:
    tabs = [quick for quick in QUICK_FILTERS if quick.code != "all"]
    occurrences = Counter(status for quick in tabs for status in quick.statuses)

    assert set(occurrences) == set(ApplicationStatus.values)  # No falta ninguno.
    assert set(occurrences.values()) == {1}  # Ninguno en dos pestañas.
    assert QUICK_FILTERS[0].code == "all"
    assert QUICK_FILTERS[0].statuses == ()


# --- Endpoint -----------------------------------------------------------------------------


@pytest.mark.usefixtures("mixed")
def test_tabs_with_counts_in_order(admin_client: APIClient) -> None:
    response = admin_client.get(QUICK_FILTERS_URL)

    assert response.status_code == 200, response.content
    body = response.json()
    assert [item["code"] for item in body] == list(EXPECTED)
    assert {item["code"]: item["count"] for item in body} == EXPECTED
    waiting = body[2]
    assert waiting == {
        "code": "waiting",
        "label": "Esperando al comprador",
        "statuses": ["WAITING_BUYER_DATA", "WAITING_DOCUMENTS"],
        "count": 2,
    }
    # La suma de las pestañas es igual a "Todas".
    assert sum(item["count"] for item in body[1:]) == body[0]["count"]


def test_counts_respect_the_scope(
    admin_client: APIClient,
    advisor_client: APIClient,
    broker_client: APIClient,
    broker_user: User,
    other_advisor: User,
    new_application: ApplicationFactory,
) -> None:
    mine = new_application(ApplicationStatus.DRAFT)
    new_application(ApplicationStatus.READY_TO_FILE, assigned_advisor=other_advisor)
    Opportunity.objects.filter(pk=mine.opportunity_id).update(origin_user=broker_user)

    none = dict.fromkeys(EXPECTED, 0)
    assert counts(admin_client) == {**none, "all": 2, "draft": 1, "ready": 1}
    assert counts(advisor_client) == {**none, "all": 1, "draft": 1}
    assert counts(broker_client) == {**none, "all": 1, "draft": 1}


def test_counts_apply_the_list_filters_and_ignore_status(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    new_application(ApplicationStatus.DRAFT, first_names="Mateo")
    new_application(
        ApplicationStatus.WAITING_DOCUMENTS,
        purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"),
    )

    used = counts(admin_client, purpose="PURCHASE_USED")
    searched = counts(admin_client, search="Mateo")
    ignored = counts(admin_client, status="READY_TO_FILE", quick_filter="ready", page_size=1)

    assert (used["all"], used["waiting"], used["draft"]) == (1, 1, 0)
    assert (searched["all"], searched["draft"], searched["waiting"]) == (1, 1, 0)
    assert (ignored["all"], ignored["draft"], ignored["waiting"]) == (2, 1, 1)
    assert_error(
        admin_client.get(QUICK_FILTERS_URL, {"purpose": "NO_EXISTE"}), 400, "VALIDATION_ERROR"
    )


def test_counts_come_from_a_single_query(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    def captured() -> list[str]:
        with CaptureQueriesContext(connection) as context:
            assert admin_client.get(QUICK_FILTERS_URL).status_code == 200
        return [query["sql"] for query in context.captured_queries]

    new_application(ApplicationStatus.DRAFT)
    one = captured()
    for status in (ApplicationStatus.FILED, ApplicationStatus.REJECTED, ApplicationStatus.DRAFT):
        new_application(status)
    many = captured()

    counting = [sql for sql in many if "credit_applications" in sql and "COUNT(" in sql]
    assert len(counting) == 1
    assert len(many) == len(one)


def test_partner_has_no_access(partner_client: APIClient) -> None:
    assert_error(partner_client.get(QUICK_FILTERS_URL), 403, "PERMISSION_DENIED")


# --- Filtro quick_filter en el listado ------------------------------------------------------


def test_quick_filter_in_the_list(
    admin_client: APIClient, mixed: dict[str, CreditApplication]
) -> None:
    waiting = {mixed["buyer_data"].code, mixed["documents"].code}

    assert list_codes(admin_client, quick_filter="waiting") == waiting
    assert list_codes(admin_client, quick_filter="ready") == {mixed["ready"].code}
    assert len(list_codes(admin_client, quick_filter="all")) == 8
    # Junto con `status`, se aplican los dos.
    both = list_codes(admin_client, quick_filter="waiting", status="WAITING_DOCUMENTS")
    assert both == {mixed["documents"].code}
    assert list_codes(admin_client, quick_filter="waiting", status="DRAFT") == set()


def test_unknown_quick_filter_is_400(admin_client: APIClient) -> None:
    body = assert_error(
        admin_client.get(APPLICATIONS_URL, {"quick_filter": "archivadas"}), 400, "VALIDATION_ERROR"
    )

    [detail] = body["details"]
    assert detail["field"] == "quick_filter"
    assert detail["message"] == (
        "Valor no permitido. Opciones: all, draft, waiting, review, ready, bank, closed."
    )
