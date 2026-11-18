"""Brechas del listado y el detalle de la solicitud (TAREA-brechas-2, parte 2): roles del
resumen de participantes, quién originó la oportunidad y consentimientos del titular."""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.crm.models import Client, Opportunity
from apps.identity.models import ConsentAction, ConsentDefinition, ConsentRecord, User
from tests.applications.buyer_access.conftest import accept_consents
from tests.applications.conftest import application_url
from tests.applications.test_applications_api import create

__all__ = ["accept_consents"]

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/applications"


def add_participant(
    application: CreditApplication, client: Client, role: str, *, active: bool = True
) -> None:
    ApplicationParticipant.objects.create(
        application=application, client=client, role=role, is_active=active
    )


def summary(api: APIClient, application: CreditApplication) -> dict:
    items = api.get(LIST_URL, {"page_size": 100}).json()["items"]
    return next(item for item in items if item["id"] == str(application.pk))["participants_summary"]


# --- participants_summary.roles -----------------------------------------------------------


def test_summary_lists_the_roles_with_labels(
    advisor_client: APIClient, application: CreditApplication, make_client: Callable[..., Client]
) -> None:
    add_participant(application, make_client(document_number="1"), ParticipantRole.CO_APPLICANT)
    add_participant(application, make_client(document_number="2"), ParticipantRole.CO_APPLICANT)
    add_participant(application, make_client(document_number="3"), ParticipantRole.SOLIDARY_DEBTOR)
    add_participant(
        application,
        make_client(document_number="4"),
        ParticipantRole.SOLIDARY_DEBTOR,
        active=False,
    )

    assert summary(advisor_client, application) == {
        "co_applicants": 2,
        "solidary_debtors": 1,
        "roles": [
            {"code": "CO_APPLICANT", "label": "Co-solicitante", "count": 2},
            {"code": "SOLIDARY_DEBTOR", "label": "Deudor solidario", "count": 1},
        ],
    }


def test_summary_without_other_participants_has_no_roles(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert summary(advisor_client, application) == {
        "co_applicants": 0,
        "solidary_debtors": 0,
        "roles": [],
    }


def test_list_queries_do_not_grow_with_the_rows(
    advisor_client: APIClient,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
) -> None:
    def add(index: int) -> None:
        application = make_application(
            make_opportunity(make_client(document_number=f"10324460{index:02d}"))
        )
        add_participant(
            application,
            make_client(document_number=f"10324470{index:02d}"),
            ParticipantRole.CO_APPLICANT,
        )

    add(0)
    with CaptureQueriesContext(connection) as one:
        assert advisor_client.get(LIST_URL).status_code == 200
    for index in range(1, 5):
        add(index)
    with CaptureQueriesContext(connection) as five:
        response = advisor_client.get(LIST_URL)

    assert len(five) == len(one)
    assert {len(item["participants_summary"]["roles"]) for item in response.json()["items"]} == {1}


# --- Detalle: originador y consentimientos -----------------------------------------------


def test_detail_names_who_originated_the_opportunity(
    advisor_client: APIClient,
    broker_user: User,
    buyer: Client,
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
    application: CreditApplication,
) -> None:
    by_broker = make_application(
        make_opportunity(
            buyer, origin_user=broker_user, origin_item=application.opportunity.origin_item
        )
    )

    with_origin = advisor_client.get(application_url(by_broker)).json()
    without = advisor_client.get(application_url(application)).json()

    assert with_origin["origin_user_name"] == broker_user.get_full_name()
    assert without["origin_user_name"] is None


def test_detail_counts_the_required_consents_of_the_primary(
    advisor_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
    accept_consents: Callable[[], None],
) -> None:
    url = application_url(application)
    assert advisor_client.get(url).json()["consents"] == {"required": 1, "accepted": 0}

    # Con un co-solicitante también es obligatoria su autorización.
    add_participant(application, make_client(document_number="5"), ParticipantRole.CO_APPLICANT)
    assert advisor_client.get(url).json()["consents"] == {"required": 2, "accepted": 0}

    accept_consents()
    assert advisor_client.get(url).json()["consents"] == {"required": 2, "accepted": 2}

    # Retirar uno deja de contarlo; un registro de otro cliente no cuenta.
    definition = ConsentDefinition.objects.get(code="DATA_PROCESSING", version=1)
    ConsentRecord.objects.create(
        consent_definition=definition,
        client=application.opportunity.client,
        application=application,
        action=ConsentAction.WITHDRAWN,
    )
    assert advisor_client.get(url).json()["consents"] == {"required": 2, "accepted": 1}


def test_created_application_has_the_new_fields(
    advisor_client: APIClient, opportunity: Opportunity
) -> None:
    response = create(advisor_client, opportunity)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["consents"] == {"required": 1, "accepted": 0}
    assert "origin_user_name" in body
