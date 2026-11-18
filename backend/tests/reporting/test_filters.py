"""Filtros comunes del dashboard: rango de fechas, ids, alcance y permisos sembrados."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.banking.models import Bank
from apps.identity.models import Role, User
from apps.partners.models import Partner, Project
from apps.reporting.filters import effective_range
from tests.reporting.conftest import FUNNEL_URL, SUMMARY_URL, add_property, at

pytestmark = pytest.mark.django_db

AppFactory = Callable[..., CreditApplication]


def _codes(response: Any) -> list[str]:
    return [detail["field"] for detail in response.json()["details"]]


# --- Permisos sembrados -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("ADMIN", {"dashboard.read", "reports.read", "reports.export", "reports.manage"}),
        ("ADVISOR", {"dashboard.read", "reports.read", "reports.export"}),
        ("INDEPENDENT_BROKER", {"dashboard.read"}),
        ("CONSTRUCTION_PARTNER", set()),
    ],
)
def test_reporting_permissions_are_seeded_per_role(role: str, expected: set[str]) -> None:
    codes = set(
        Role.objects.get(code=role)
        .permission_assignments.filter(permission__module="reporting")
        .values_list("permission__code", flat=True)
    )

    assert codes == expected


# --- Rango de fechas ----------------------------------------------------------------------


def test_without_dates_the_range_is_the_current_month(advisor_client: APIClient) -> None:
    today = timezone.localdate()

    body = advisor_client.get(SUMMARY_URL).json()

    assert body["period"] == {
        "date_from": today.replace(day=1).isoformat(),
        "date_to": today.isoformat(),
    }


def test_only_date_to_starts_on_the_first_day_of_its_month(advisor_client: APIClient) -> None:
    body = advisor_client.get(SUMMARY_URL, {"date_to": "2026-03-20"}).json()

    assert body["period"] == {"date_from": "2026-03-01", "date_to": "2026-03-20"}


def test_only_date_from_ends_today(advisor_client: APIClient) -> None:
    today = timezone.localdate()

    body = advisor_client.get(SUMMARY_URL, {"date_from": "2026-01-15"}).json()

    assert body["period"] == {"date_from": "2026-01-15", "date_to": today.isoformat()}


def test_a_future_date_to_is_clipped_to_today(advisor_client: APIClient) -> None:
    today = timezone.localdate()
    future = today + timedelta(days=40)

    response = advisor_client.get(
        SUMMARY_URL, {"date_from": today.replace(day=1).isoformat(), "date_to": future.isoformat()}
    )

    assert response.status_code == 200
    assert response.json()["period"]["date_to"] == today.isoformat()


def test_date_from_after_date_to_is_rejected(advisor_client: APIClient) -> None:
    response = advisor_client.get(SUMMARY_URL, {"date_from": "2026-03-10", "date_to": "2026-03-01"})

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert _codes(response) == ["date_from"]


def test_a_range_longer_than_366_days_is_rejected(advisor_client: APIClient) -> None:
    response = advisor_client.get(FUNNEL_URL, {"date_from": "2025-01-01", "date_to": "2026-01-02"})

    assert response.status_code == 400
    assert _codes(response) == ["date_to"]


def test_a_range_of_exactly_366_days_is_accepted() -> None:
    assert effective_range(date(2024, 1, 1), date(2024, 12, 31)) == (
        date(2024, 1, 1),
        date(2024, 12, 31),
    )


def test_a_malformed_date_is_rejected(advisor_client: APIClient) -> None:
    response = advisor_client.get(SUMMARY_URL, {"date_from": "17/11/2026"})

    assert response.status_code == 400
    assert _codes(response) == ["date_from"]


def test_the_range_uses_the_bogota_day(
    admin_client: APIClient, make_report_application: AppFactory
) -> None:
    # 23:30 del 31 de marzo en Bogotá ya es 1 de abril en UTC: sigue siendo de marzo.
    make_report_application(created_at=at(date(2026, 3, 31), hour=23))

    march = admin_client.get(SUMMARY_URL, {"date_from": "2026-03-01", "date_to": "2026-03-31"})
    april = admin_client.get(SUMMARY_URL, {"date_from": "2026-04-01", "date_to": "2026-04-30"})

    assert march.json()["applications_created"] == 1
    assert april.json()["applications_created"] == 0


# --- Ids y códigos ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["advisor_id", "partner_id", "project_id", "bank_id"])
def test_an_unknown_id_is_a_validation_error(admin_client: APIClient, name: str) -> None:
    response = admin_client.get(SUMMARY_URL, {name: "00000000-0000-0000-0000-000000000000"})

    assert response.status_code == 400
    assert _codes(response) == [name]


def test_a_malformed_id_is_a_validation_error(admin_client: APIClient) -> None:
    response = admin_client.get(SUMMARY_URL, {"bank_id": "no-es-uuid"})

    assert response.status_code == 400
    assert _codes(response) == ["bank_id"]


def test_an_unknown_purpose_code_is_a_validation_error(admin_client: APIClient) -> None:
    response = admin_client.get(SUMMARY_URL, {"purpose_code": "YACHT"})

    assert response.status_code == 400
    assert _codes(response) == ["purpose_code"]


# --- Alcance de los filtros ---------------------------------------------------------------


def _assert_out_of_scope(response: Any, field: str) -> None:
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "FILTER_OUT_OF_SCOPE"
    assert [detail["field"] for detail in body["details"]] == [field]


def test_an_advisor_cannot_filter_by_another_advisor(
    advisor_client: APIClient, other_advisor: User
) -> None:
    response = advisor_client.get(SUMMARY_URL, {"advisor_id": str(other_advisor.pk)})

    _assert_out_of_scope(response, "advisor_id")


def test_an_advisor_cannot_probe_unknown_advisor_ids(advisor_client: APIClient) -> None:
    """El alcance se revisa antes que la existencia: no confirma qué ids existen."""
    response = advisor_client.get(
        SUMMARY_URL, {"advisor_id": "00000000-0000-0000-0000-000000000000"}
    )

    _assert_out_of_scope(response, "advisor_id")


def test_an_advisor_can_filter_by_itself(advisor_client: APIClient, advisor_user: User) -> None:
    response = advisor_client.get(SUMMARY_URL, {"advisor_id": str(advisor_user.pk)})

    assert response.status_code == 200


@pytest.mark.parametrize("name", ["advisor_id", "partner_id", "project_id"])
def test_a_broker_cannot_use_operation_filters(
    broker_client: APIClient,
    advisor_user: User,
    partner: Partner,
    make_project: Callable[..., Project],
    name: str,
) -> None:
    ids = {
        "advisor_id": advisor_user.pk,
        "partner_id": partner.pk,
        "project_id": make_project().pk,
    }

    response = broker_client.get(FUNNEL_URL, {name: str(ids[name])})

    _assert_out_of_scope(response, name)


def test_a_broker_can_filter_by_bank_and_purpose(broker_client: APIClient) -> None:
    bank = Bank.objects.get(code="BANCOLOMBIA")

    response = broker_client.get(
        FUNNEL_URL, {"bank_id": str(bank.pk), "purpose_code": "PURCHASE_NEW"}
    )

    assert response.status_code == 200


def test_the_admin_can_use_every_filter(
    admin_client: APIClient,
    advisor_user: User,
    partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    bank = Bank.objects.get(code="BANCOLOMBIA")

    response = admin_client.get(
        SUMMARY_URL,
        {
            "advisor_id": str(advisor_user.pk),
            "partner_id": str(partner.pk),
            "project_id": str(make_project().pk),
            "bank_id": str(bank.pk),
            "purpose_code": "PURCHASE_NEW",
        },
    )

    assert response.status_code == 200


# --- Ruta del proyecto --------------------------------------------------------------------


def test_project_and_partner_come_from_the_property_or_else_the_opportunity(
    admin_client: APIClient,
    make_report_application: AppFactory,
    make_project: Callable[..., Project],
    partner: Partner,
) -> None:
    verona = make_project(name="Verona 118")
    other_partner = Partner.objects.create(legal_name="Otra Constructora", tax_id="900999999-1")
    altos = make_project(name="Altos")
    Project.objects.filter(pk=altos.pk).update(partner=other_partner)
    # Inmueble en Verona aunque la oportunidad llegó por Altos: manda el inmueble.
    by_property = make_report_application(opportunity_project=altos)
    add_property(by_property, verona)
    # Sin inmueble: cuenta el proyecto de la oportunidad.
    make_report_application(opportunity_project=verona)
    # Inmueble sin proyecto: también cae al de la oportunidad.
    without_project = make_report_application(opportunity_project=altos)
    add_property(without_project, None)

    def created(params: dict[str, str]) -> int:
        return int(admin_client.get(SUMMARY_URL, params).json()["applications_created"])

    assert created({"project_id": str(verona.pk)}) == 2
    assert created({"project_id": str(altos.pk)}) == 1
    assert created({"partner_id": str(partner.pk)}) == 2
    assert created({"partner_id": str(other_partner.pk)}) == 1
