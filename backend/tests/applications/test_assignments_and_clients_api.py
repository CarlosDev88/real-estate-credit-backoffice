"""Reasignación (API §16.1 `/assignments`) y solicitudes del cliente (API §13)."""

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationAssignment,
    ApplicationParticipant,
    CreditApplication,
    ParticipantRole,
)
from apps.applications.signals import application_assigned
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import application_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db


def assign(client: APIClient, application: CreditApplication, advisor: User, **extra: Any) -> Any:
    return client.post(
        application_url(application, "/assignments"),
        {"advisor_id": str(advisor.id), **extra},
        format="json",
    )


def client_applications_url(client: Client) -> str:
    return f"/api/v1/clients/{client.id}/applications"


@pytest.fixture
def current_assignment(application: CreditApplication, advisor_user: User) -> ApplicationAssignment:
    return ApplicationAssignment.objects.create(application=application, advisor=advisor_user)


# --- Reasignación -----------------------------------------------------------------------


def test_reassignment_keeps_the_history(
    admin_client: APIClient,
    admin_user: User,
    application: CreditApplication,
    current_assignment: ApplicationAssignment,
    other_advisor: User,
) -> None:
    response = assign(admin_client, application, other_advisor, reason="Vacaciones")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["assigned_advisor"]["id"] == str(other_advisor.id)
    assert body["version"] == 1  # El responsable no es un dato del crédito.
    assert [item["advisor"]["id"] for item in body["assignments"]] == [
        str(other_advisor.id),
        str(current_assignment.advisor_id),
    ]
    current_assignment.refresh_from_db()
    assert current_assignment.ended_at is not None
    new = ApplicationAssignment.objects.get(application=application, ended_at__isnull=True)
    assert (new.advisor, new.assigned_by, new.reason) == (other_advisor, admin_user, "Vacaciones")


def test_reassignment_sends_an_event(
    admin_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    current_assignment: ApplicationAssignment,
    other_advisor: User,
) -> None:
    received: list[dict[str, Any]] = []

    def on_assigned(**kwargs: Any) -> None:
        received.append(kwargs)

    application_assigned.connect(on_assigned)
    try:
        assign(admin_client, application, other_advisor)
    finally:
        application_assigned.disconnect(on_assigned)

    assert [(event["previous_advisor_id"], event["advisor_id"]) for event in received] == [
        (advisor_user.pk, other_advisor.pk)
    ]


def test_advisor_who_hands_over_loses_access(
    advisor_client: APIClient,
    application: CreditApplication,
    current_assignment: ApplicationAssignment,
    other_advisor: User,
) -> None:
    response = assign(advisor_client, application, other_advisor)

    assert response.status_code == 204
    assert advisor_client.get(application_url(application)).status_code == 404


def test_same_advisor_is_a_no_op(
    admin_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    current_assignment: ApplicationAssignment,
) -> None:
    assert assign(admin_client, application, advisor_user).status_code == 200
    assert ApplicationAssignment.objects.filter(application=application).count() == 1


def test_new_advisor_must_be_eligible(
    admin_client: APIClient, application: CreditApplication, broker_user: User
) -> None:
    assert_error(assign(admin_client, application, broker_user), 422, "ADVISOR_NOT_ELIGIBLE")


@pytest.mark.parametrize("status", ["FILED", "CREDIT_ANALYSIS"])
def test_filed_applications_can_be_reassigned(
    admin_client: APIClient, application: CreditApplication, other_advisor: User, status: str
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)
    assert assign(admin_client, application, other_advisor).status_code == 200


@pytest.mark.parametrize("status", ["DISBURSED", "REJECTED", "CANCELLED"])
def test_finished_applications_cannot_be_reassigned(
    admin_client: APIClient, application: CreditApplication, other_advisor: User, status: str
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)
    assert_error(assign(admin_client, application, other_advisor), 409, "APPLICATION_CLOSED")


def test_unknown_advisor_is_rejected(
    admin_client: APIClient, application: CreditApplication
) -> None:
    response = admin_client.post(
        application_url(application, "/assignments"),
        {"advisor_id": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "advisor_id"


def test_broker_cannot_reassign(
    broker_client: APIClient, application: CreditApplication, other_advisor: User
) -> None:
    assert_error(assign(broker_client, application, other_advisor), 403, "PERMISSION_DENIED")


def test_out_of_scope_reassignment_returns_404(
    other_advisor_client: APIClient, application: CreditApplication, other_advisor: User
) -> None:
    response = assign(other_advisor_client, application, other_advisor)
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


# --- Solicitudes del cliente ------------------------------------------------------------


def test_client_applications_include_every_role(
    admin_client: APIClient,
    buyer: Client,
    application: CreditApplication,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
) -> None:
    # El comprador también es co-solicitante en la solicitud de otra persona.
    other = make_application(make_opportunity(make_client(document_number="80123456")))
    ApplicationParticipant.objects.create(
        application=other, client=buyer, role=ParticipantRole.CO_APPLICANT
    )
    # Y fue retirado de una tercera.
    retired = make_application(make_opportunity(make_client(document_number="52123456")))
    ApplicationParticipant.objects.create(
        application=retired, client=buyer, role=ParticipantRole.SOLIDARY_DEBTOR, is_active=False
    )

    response = admin_client.get(client_applications_url(buyer))

    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["items"]} == {str(application.id), str(other.id)}
    assert body["total"] == 2


def test_client_applications_filter_by_status(
    admin_client: APIClient, buyer: Client, application: CreditApplication
) -> None:
    assert (
        admin_client.get(client_applications_url(buyer), {"status": "FILED"}).json()["items"] == []
    )
    CreditApplication.objects.filter(pk=application.pk).update(status=ApplicationStatus.FILED)
    body = admin_client.get(client_applications_url(buyer), {"status": "FILED"}).json()
    assert [item["id"] for item in body["items"]] == [str(application.id)]

    response = admin_client.get(client_applications_url(buyer), {"status": "PAUSED"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_client_applications_respect_the_scope(
    other_advisor_client: APIClient,
    advisor_client: APIClient,
    buyer: Client,
    application: CreditApplication,
) -> None:
    assert [
        item["id"] for item in advisor_client.get(client_applications_url(buyer)).json()["items"]
    ] == [str(application.id)]
    # La segunda asesora no ve al cliente.
    assert_error(
        other_advisor_client.get(client_applications_url(buyer)), 404, "RESOURCE_NOT_FOUND"
    )


def test_broker_gets_the_summary_of_client_applications(
    broker_client: APIClient,
    broker_user: User,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    buyer: Client,
) -> None:
    mine = make_application(make_opportunity(buyer, origin_user=broker_user))

    body = broker_client.get(client_applications_url(buyer)).json()

    assert [item["id"] for item in body["items"]] == [str(mine.id)]
    assert "applicant" not in body["items"][0]
    assert "status_label" in body["items"][0]


def test_partner_cannot_list_client_applications(
    partner_client: APIClient, buyer: Client, application: CreditApplication
) -> None:
    assert_error(partner_client.get(client_applications_url(buyer)), 403, "PERMISSION_DENIED")
