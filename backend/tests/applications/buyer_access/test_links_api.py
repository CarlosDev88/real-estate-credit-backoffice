"""Emisión, listado y revocación de enlaces del comprador (API §8, Parte 2)."""

import json
import logging
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import BuyerAccessLink, BuyerAccessLinkStatus, BuyerSession, User
from apps.identity.tokens import hash_token
from tests.applications.conftest import application_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

LINK_URL = "/api/v1/buyer-access-links"
TOKEN_IN_URL = re.compile(r"\?token=([A-Za-z0-9_\-]+)$")


def links_url(application: CreditApplication) -> str:
    return application_url(application, "/buyer-access-links")


def issue(client: APIClient, application: CreditApplication, **payload: Any) -> Any:
    # El correo sale en `on_commit`, y en pruebas la transacción nunca confirma.
    with TestCase.captureOnCommitCallbacks(execute=True):
        return client.post(links_url(application), payload)


def token_of(response: Any) -> str:
    match = TOKEN_IN_URL.search(response.json()["url"])
    assert match, response.json()
    return match.group(1)


@pytest.fixture
def broker_application(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
    broker_user: User,
) -> CreditApplication:
    """Solicitud de una oportunidad que originó el broker."""
    client = make_client(document_number="80123456", first_names="Pedro")
    return make_application(make_opportunity(client, origin_user=broker_user))


def expire(link: BuyerAccessLink) -> None:
    """Mueve las fechas al pasado sin violar `expires_at > created_at`."""
    past = timezone.now() - timedelta(days=5)
    BuyerAccessLink.objects.filter(pk=link.pk).update(
        created_at=past, expires_at=past + timedelta(hours=72)
    )


# --- Emisión ----------------------------------------------------------------------------


def test_advisor_issues_a_single_use_link_for_the_primary(
    advisor_client: APIClient, application: CreditApplication, advisor_user: User
) -> None:
    before = timezone.now()
    response = issue(advisor_client, application)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["application_id"] == str(application.id)
    assert body["client_id"] == str(application.opportunity.client_id)
    assert body["status"] == "PENDING"
    assert body["delivery_channel"] == {"code": "COPY_LINK", "label": "Copiar enlace"}
    assert body["created_by"] == {"id": str(advisor_user.id), "name": "Andrea García"}
    assert body["session"] is None
    assert body["url"].startswith("http://localhost:3000/acceso?token=")

    link = BuyerAccessLink.objects.get(pk=body["id"])
    assert link.token_hash == hash_token(token_of(response))
    assert timedelta(hours=72) <= link.expires_at - before < timedelta(hours=72, minutes=1)
    assert mail.outbox == []


@pytest.mark.parametrize("hours", [1, 168])
def test_expiry_can_be_chosen_within_the_limits(
    advisor_client: APIClient, application: CreditApplication, hours: int
) -> None:
    response = issue(advisor_client, application, expires_in_hours=hours)

    assert response.status_code == 201, response.content
    link = BuyerAccessLink.objects.get(pk=response.json()["id"])
    assert (link.expires_at - link.created_at).total_seconds() == pytest.approx(hours * 3600, abs=5)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"expires_in_hours": 0}, "expires_in_hours"),
        ({"expires_in_hours": 169}, "expires_in_hours"),
        ({"delivery_channel": "WHATSAPP"}, "delivery_channel"),
        ({"client_id": "8d0e1c64-9d55-4a8e-9f0e-3f1d2b0c4a11"}, "client_id"),
    ],
)
def test_invalid_input_is_rejected(
    advisor_client: APIClient, application: CreditApplication, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(issue(advisor_client, application, **payload), 400, "VALIDATION_ERROR")
    assert [detail["field"] for detail in body["details"]] == [field]
    assert not BuyerAccessLink.objects.exists()


def test_a_new_link_revokes_pending_ones_but_keeps_open_sessions(
    advisor_client: APIClient,
    application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
    make_session: Callable[..., BuyerSession],
) -> None:
    pending = make_link()
    expired = make_link()
    expire(expired)
    session = make_session()

    new_id = issue(advisor_client, application).json()["id"]

    pending.refresh_from_db()
    expired.refresh_from_db()
    session.refresh_from_db()
    assert pending.status == BuyerAccessLinkStatus.REVOKED
    assert expired.status == BuyerAccessLinkStatus.EXPIRED
    assert session.is_active_at()
    assert BuyerAccessLink.objects.get(pk=new_id).status == BuyerAccessLinkStatus.PENDING


def test_email_channel_sends_the_link_to_the_primary(
    advisor_client: APIClient, application: CreditApplication, buyer: Client
) -> None:
    buyer.email = "laura@example.com"
    buyer.save()

    response = issue(advisor_client, application, delivery_channel="EMAIL", expires_in_hours=48)

    assert response.status_code == 201, response.content
    assert response.json()["delivery_channel"]["code"] == "EMAIL"
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["laura@example.com"]
    assert "Hola Laura" in message.body
    assert "vence en 48 horas" in message.body
    assert response.json()["url"] in message.body
    assert buyer.document_number not in message.body


def test_email_channel_needs_the_primary_email(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    body = assert_error(
        issue(advisor_client, application, delivery_channel="EMAIL"), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "delivery_channel"
    assert not BuyerAccessLink.objects.exists()
    assert mail.outbox == []


def test_links_can_be_issued_after_filing(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=ApplicationStatus.FILED)
    assert issue(advisor_client, application).status_code == 201


def test_a_closed_application_does_not_get_links(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(
        status=ApplicationStatus.CANCELLED, closed_at=timezone.now()
    )
    assert_error(issue(advisor_client, application), 409, "APPLICATION_CLOSED")


def test_broker_issues_links_for_the_applications_it_originated(
    broker_client: APIClient,
    broker_application: CreditApplication,
    application: CreditApplication,
) -> None:
    response = issue(broker_client, broker_application)
    assert response.status_code == 201, response.content
    # La respuesta no trae datos del expediente.
    assert set(response.json()) == {
        "id",
        "application_id",
        "client_id",
        "status",
        "delivery_channel",
        "created_by",
        "created_at",
        "expires_at",
        "consumed_at",
        "revoked_at",
        "session",
        "url",
    }

    assert_error(issue(broker_client, application), 404, "RESOURCE_NOT_FOUND")


def test_out_of_scope_actors_cannot_issue(
    other_advisor_client: APIClient,
    partner_client: APIClient,
    admin_client: APIClient,
    application: CreditApplication,
) -> None:
    assert_error(issue(other_advisor_client, application), 404, "RESOURCE_NOT_FOUND")
    assert_error(issue(partner_client, application), 403, "PERMISSION_DENIED")
    assert_error(issue(APIClient(), application), 401, "NOT_AUTHENTICATED")
    assert issue(admin_client, application).status_code == 201


def test_issuing_is_rate_limited_per_issuer_and_application(
    advisor_client: APIClient,
    application: CreditApplication,
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
    make_application: Callable[..., CreditApplication],
) -> None:
    for _ in range(3):
        assert issue(advisor_client, application).status_code == 201

    response = issue(advisor_client, application)
    assert_error(response, 429, "RATE_LIMITED")
    assert int(response["Retry-After"]) > 0

    # Otra solicitud tiene su propio contador, y listar no consume el límite.
    other = make_application(make_opportunity(make_client(document_number="52000111")))
    assert issue(advisor_client, other).status_code == 201
    assert advisor_client.get(links_url(application)).status_code == 200


def test_the_token_is_never_logged(
    advisor_client: APIClient, application: CreditApplication, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = issue(advisor_client, application)
        advisor_client.get(links_url(application))

    token = token_of(response)
    assert caplog.records, "se esperaba al menos el registro de la emisión"
    assert token not in caplog.text
    assert hash_token(token) not in caplog.text


# --- Listado ----------------------------------------------------------------------------


def test_history_has_no_token_and_shows_the_session(
    advisor_client: APIClient,
    application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
    make_session: Callable[..., BuyerSession],
) -> None:
    session = make_session()
    token = token_of(issue(advisor_client, application))

    response = advisor_client.get(links_url(application))

    assert response.status_code == 200
    raw = json.dumps(response.json())
    assert token not in raw
    assert hash_token(token) not in raw
    assert "url" not in raw
    assert "token_hash" not in raw

    items = response.json()["items"]
    assert [item["status"] for item in items] == ["PENDING", "CONSUMED"]
    consumed = items[1]
    assert consumed["session"]["id"] == str(session.id)
    assert consumed["session"]["is_active"] is True
    assert set(consumed["session"]) == {
        "id",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_seen_at",
        "is_active",
    }


@pytest.mark.parametrize("status", ["PENDING", "CONSUMED", "REVOKED", "EXPIRED"])
def test_history_filters_by_status(
    advisor_client: APIClient,
    application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
    status: str,
) -> None:
    now = timezone.now()
    links = {
        "PENDING": make_link(),
        "CONSUMED": make_link(consumed_at=now),
        "REVOKED": make_link(revoked_at=now),
        "EXPIRED": make_link(),
    }
    expire(links["EXPIRED"])

    response = advisor_client.get(links_url(application), {"status": status})

    assert [item["id"] for item in response.json()["items"]] == [str(links[status].id)]


def test_history_rejects_an_unknown_status(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    body = assert_error(
        advisor_client.get(links_url(application), {"status": "USED"}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "status"


def test_history_follows_the_application_scope(
    broker_client: APIClient,
    other_advisor_client: APIClient,
    partner_client: APIClient,
    broker_application: CreditApplication,
    application: CreditApplication,
) -> None:
    assert broker_client.get(links_url(broker_application)).status_code == 200
    assert_error(broker_client.get(links_url(application)), 404, "RESOURCE_NOT_FOUND")
    assert_error(other_advisor_client.get(links_url(application)), 404, "RESOURCE_NOT_FOUND")
    assert_error(partner_client.get(links_url(application)), 403, "PERMISSION_DENIED")


# --- Revocación -------------------------------------------------------------------------


def revoke(client: APIClient, link: BuyerAccessLink) -> Any:
    return client.delete(f"{LINK_URL}/{link.id}")


def test_revoking_a_pending_link(
    advisor_client: APIClient, make_link: Callable[..., BuyerAccessLink]
) -> None:
    link = make_link()

    assert revoke(advisor_client, link).status_code == 204
    link.refresh_from_db()
    assert link.status == BuyerAccessLinkStatus.REVOKED


def test_revoking_a_consumed_link_closes_its_session(
    advisor_client: APIClient, make_session: Callable[..., BuyerSession]
) -> None:
    session = make_session()

    assert revoke(advisor_client, session.access_link).status_code == 204
    session.refresh_from_db()
    session.access_link.refresh_from_db()
    assert not session.is_active_at()
    assert session.access_link.status == BuyerAccessLinkStatus.CONSUMED


def test_revoking_is_idempotent(
    advisor_client: APIClient,
    make_link: Callable[..., BuyerAccessLink],
    make_session: Callable[..., BuyerSession],
) -> None:
    revoked_at = timezone.now() - timedelta(minutes=5)
    revoked = make_link(revoked_at=revoked_at)
    expired = make_link()
    expire(expired)
    session = make_session(revoked_at=revoked_at)

    for link in (revoked, expired, session.access_link):
        assert revoke(advisor_client, link).status_code == 204

    revoked.refresh_from_db()
    expired.refresh_from_db()
    session.refresh_from_db()
    assert revoked.revoked_at == revoked_at
    assert expired.revoked_at is None
    assert session.revoked_at == revoked_at


def test_broker_only_revokes_the_links_it_issued(
    broker_client: APIClient,
    broker_user: User,
    advisor_user: User,
    broker_application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
) -> None:
    own = make_link(application=broker_application, created_by=broker_user)
    from_advisor = make_link(application=broker_application, created_by=advisor_user)

    assert_error(revoke(broker_client, from_advisor), 403, "PERMISSION_DENIED")
    assert revoke(broker_client, own).status_code == 204
    from_advisor.refresh_from_db()
    assert from_advisor.status == BuyerAccessLinkStatus.PENDING


def test_out_of_scope_actors_cannot_revoke(
    broker_client: APIClient,
    other_advisor_client: APIClient,
    partner_client: APIClient,
    admin_client: APIClient,
    make_link: Callable[..., BuyerAccessLink],
) -> None:
    link = make_link()

    assert_error(revoke(broker_client, link), 404, "RESOURCE_NOT_FOUND")
    assert_error(revoke(other_advisor_client, link), 404, "RESOURCE_NOT_FOUND")
    assert_error(revoke(partner_client, link), 403, "PERMISSION_DENIED")
    assert revoke(admin_client, link).status_code == 204
