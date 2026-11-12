"""Datos del listado de solicitudes (TAREA-applications-listado, Parte 1): tipo de
crédito y su filtro, monto, co-solicitantes, ``status_label``, órdenes nuevos y la
validación de los filtros por código de catálogo."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancingPreference,
    ParticipantRole,
)
from apps.applications.serializers import ApplicationSerializer
from apps.banking.models import Bank, BankProduct
from apps.catalogs.models import CatalogItem
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import APPLICATIONS_URL, catalog_item, seeded_product
from tests.applications.test_applications_api import SUMMARY_KEYS
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

ApplicationFactory = Callable[..., CreditApplication]


@pytest.fixture
def new_application(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: ApplicationFactory,
) -> ApplicationFactory:
    """Solicitud con su propio cliente (documento distinto en cada llamada)."""
    counter = iter(range(1, 1000))

    def _new_application(
        first_names: str = "Laura", last_names: str = "Gómez Vélez", **extra: Any
    ) -> CreditApplication:
        number = next(counter)
        client = make_client(
            document_number=f"10{number:08}", first_names=first_names, last_names=last_names
        )
        return make_application(make_opportunity(client), **extra)

    return _new_application


def finance(application: CreditApplication, amount: int) -> FinancingPreference:
    return FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "BANK_CREDIT"),
        requested_amount_cop=amount,
        term_months=240,
    )


def add_participant(
    application: CreditApplication,
    make_client: Callable[..., Client],
    role: str,
    document_number: str,
    *,
    is_active: bool = True,
) -> ApplicationParticipant:
    client = make_client(document_number=document_number, first_names="Andrés")
    return ApplicationParticipant.objects.create(
        application=application, client=client, role=role, is_active=is_active
    )


def leasing_product() -> BankProduct:
    bank = Bank.objects.create(code="BANCO_LEASING", name="Banco Leasing")
    return BankProduct.objects.create(
        bank=bank,
        code="LEASING",
        name="Leasing habitacional",
        product_type_item=catalog_item("bank_product_type", "HOUSING_LEASING"),
        valid_from=date(2026, 1, 1),
    )


def items(client: APIClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get(APPLICATIONS_URL, params)
    assert response.status_code == 200, response.content
    return list(response.json()["items"])


def codes(client: APIClient, **params: Any) -> list[str]:
    return [item["code"] for item in items(client, **params)]


# --- Campos nuevos ------------------------------------------------------------------------


def test_row_has_type_amount_participants_and_status_label(
    admin_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(bank_product=seeded_product())
    finance(application, 294_000_000)
    add_participant(application, make_client, ParticipantRole.CO_APPLICANT, "80123456")
    add_participant(application, make_client, ParticipantRole.SOLIDARY_DEBTOR, "80123457")
    # Un co-solicitante retirado no cuenta.
    add_participant(
        application, make_client, ParticipantRole.CO_APPLICANT, "80123458", is_active=False
    )

    [row] = items(admin_client)

    assert row["status"] == "DRAFT"
    assert row["status_label"] == "Borrador"
    assert row["bank_product"]["product_type"] == {
        "code": "MORTGAGE",
        "label": "Crédito hipotecario",
    }
    assert row["requested_amount_cop"] == 294_000_000
    assert row["participants_summary"] == {"co_applicants": 1, "solidary_debtors": 1}


def test_fields_without_product_or_financing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    [row] = items(advisor_client)

    assert row["bank_product"] is None
    assert row["requested_amount_cop"] is None
    assert row["participants_summary"] == {"co_applicants": 0, "solidary_debtors": 0}


def test_detail_and_client_list_carry_the_same_fields(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    finance(application, 150_000_000)

    detail = advisor_client.get(f"{APPLICATIONS_URL}/{application.id}").json()
    client_list = advisor_client.get(
        f"/api/v1/clients/{application.opportunity.client_id}/applications"
    ).json()["items"]

    for body in (detail, client_list[0]):
        assert body["status_label"] == "Borrador"
        assert body["requested_amount_cop"] == 150_000_000
        assert body["participants_summary"] == {"co_applicants": 0, "solidary_debtors": 0}


def test_participants_summary_without_annotations(
    application: CreditApplication, make_client: Callable[..., Client]
) -> None:
    """Una instancia que no salió de ``applications_queryset`` cuenta con consultas."""
    add_participant(application, make_client, ParticipantRole.SOLIDARY_DEBTOR, "80123459")
    plain = CreditApplication.objects.get(pk=application.pk)

    data = ApplicationSerializer(plain).data

    assert data["participants_summary"] == {"co_applicants": 0, "solidary_debtors": 1}


def test_broker_summary_does_not_change(
    broker_client: APIClient,
    broker_user: User,
    new_application: ApplicationFactory,
) -> None:
    application = new_application()
    Opportunity.objects.filter(pk=application.opportunity_id).update(origin_user=broker_user)
    finance(application, 294_000_000)

    [row] = items(broker_client)

    assert set(row) == SUMMARY_KEYS
    assert "requested_amount_cop" not in row
    assert "participants_summary" not in row


# --- Filtros por código de catálogo -------------------------------------------------------


def test_product_type_filter(admin_client: APIClient, new_application: ApplicationFactory) -> None:
    mortgage = new_application(bank_product=seeded_product())
    leasing = new_application(bank_product=leasing_product())
    new_application()  # Sin producto: no tiene tipo de crédito.

    assert codes(admin_client, product_type="MORTGAGE") == [mortgage.code]
    assert codes(admin_client, product_type="HOUSING_LEASING") == [leasing.code]


def test_purpose_and_origin_filters_accept_known_codes(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    used = new_application(purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"))
    new_application()

    assert codes(admin_client, purpose="PURCHASE_USED") == [used.code]
    assert len(codes(admin_client, origin="DIRECT")) == 2


def test_inactive_catalog_codes_still_filter_the_history(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    used = new_application(purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"))
    CatalogItem.objects.filter(catalog__code="loan_purpose", code="PURCHASE_USED").update(
        is_active=False
    )

    assert codes(admin_client, purpose="PURCHASE_USED") == [used.code]


@pytest.mark.parametrize(
    ("param", "catalog_code"),
    [
        ("purpose", "loan_purpose"),
        ("origin", "lead_origin"),
        ("product_type", "bank_product_type"),
    ],
)
def test_unknown_catalog_codes_are_400(
    admin_client: APIClient, param: str, catalog_code: str
) -> None:
    body = assert_error(
        admin_client.get(APPLICATIONS_URL, {param: "NO_EXISTE"}), 400, "VALIDATION_ERROR"
    )

    [detail] = body["details"]
    assert detail["field"] == param
    known = CatalogItem.objects.filter(catalog__code=catalog_code).order_by("code")
    assert detail["message"] == (
        f"Valor no permitido. Opciones: {', '.join(item.code for item in known)}."
    )


def test_a_code_from_another_catalog_is_rejected(admin_client: APIClient) -> None:
    # MORTGAGE existe, pero en `bank_product_type`, no en `loan_purpose`.
    assert_error(
        admin_client.get(APPLICATIONS_URL, {"purpose": "MORTGAGE"}), 400, "VALIDATION_ERROR"
    )


# --- Orden --------------------------------------------------------------------------------


def test_order_by_requested_amount_with_nulls_last(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    small = new_application()
    finance(small, 100_000_000)
    large = new_application()
    finance(large, 300_000_000)
    without = new_application()

    assert codes(admin_client, ordering="requested_amount") == [
        small.code,
        large.code,
        without.code,
    ]
    assert codes(admin_client, ordering="-requested_amount") == [
        large.code,
        small.code,
        without.code,
    ]


def test_order_by_bank_name_with_nulls_last(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    bancolombia = new_application(bank_product=seeded_product("BANCOLOMBIA"))
    leasing = new_application(bank_product=leasing_product())  # "Banco Leasing"
    without = new_application()

    assert codes(admin_client, ordering="bank_name") == [
        leasing.code,
        bancolombia.code,
        without.code,
    ]
    assert codes(admin_client, ordering="-bank_name") == [
        bancolombia.code,
        leasing.code,
        without.code,
    ]


def test_order_by_applicant_name(
    admin_client: APIClient, new_application: ApplicationFactory
) -> None:
    zoe = new_application(first_names="Zoe", last_names="Arias")
    ana_ruiz = new_application(first_names="Ana", last_names="Ruiz")
    ana_diaz = new_application(first_names="Ana", last_names="Díaz")

    assert codes(admin_client, ordering="applicant_name") == [
        ana_diaz.code,
        ana_ruiz.code,
        zoe.code,
    ]
    assert codes(admin_client, ordering="-applicant_name")[0] == zoe.code


def test_unknown_ordering_is_still_400(admin_client: APIClient) -> None:
    assert_error(
        admin_client.get(APPLICATIONS_URL, {"ordering": "completeness_pct"}),
        400,
        "VALIDATION_ERROR",
    )


# --- Consultas ----------------------------------------------------------------------------


def list_queries(client: APIClient) -> int:
    with CaptureQueriesContext(connection) as context:
        response = client.get(APPLICATIONS_URL, {"page_size": 25})
    assert response.status_code == 200, response.content
    return len(context.captured_queries)


@pytest.mark.parametrize("user_client", ["admin_client", "advisor_client"])
def test_list_queries_do_not_grow_with_rows(
    request: pytest.FixtureRequest,
    user_client: str,
    new_application: ApplicationFactory,
    make_client: Callable[..., Client],
) -> None:
    client: APIClient = request.getfixturevalue(user_client)

    def full_row(index: int) -> None:
        application = new_application(bank_product=seeded_product())
        finance(application, 100_000_000 + index)
        add_participant(application, make_client, ParticipantRole.CO_APPLICANT, f"7{index:07}")

    full_row(0)
    one_row = list_queries(client)
    for index in range(1, 25):
        full_row(index)

    assert len(items(client, page_size=25)) == 25
    assert list_queries(client) == one_row
