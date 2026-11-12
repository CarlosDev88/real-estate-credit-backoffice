"""Consumo del enlace, sesión del comprador y lectura de su proceso (API §8, Parte 3)."""

import logging
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancingPreference,
    ParticipantRole,
    Property,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity import buyer_portal
from apps.identity.cookies import buyer_session_cookie_name
from apps.identity.models import BuyerAccessLink, BuyerSession
from apps.identity.tokens import generate_opaque_token, hash_token
from tests.applications.buyer_access.conftest import (
    CONSUME_URL,
    LinkFactory,
    consume,
    pending_token,
)
from tests.applications.conftest import application_url, catalog_item
from tests.helpers import assert_error, cookie_was_cleared, csrf_token

pytestmark = pytest.mark.django_db

SESSION_URL = "/api/v1/buyer/session"
LOGOUT_URL = "/api/v1/buyer/session/logout"
PROCESSES_URL = "/api/v1/buyer/processes"
BUYER_APPLICATIONS_URL = "/api/v1/buyer/applications"


def buyer_application_url(application: CreditApplication | uuid.UUID) -> str:
    application_id = application if isinstance(application, uuid.UUID) else application.pk
    return f"{BUYER_APPLICATIONS_URL}/{application_id}"


def session_token(client: APIClient) -> str:
    return client.cookies[buyer_session_cookie_name()].value


def set_status(application: CreditApplication, status: str) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)


def expire_link(link: BuyerAccessLink) -> None:
    """Mueve las fechas al pasado sin violar `expires_at > created_at`."""
    past = timezone.now() - timedelta(days=5)
    BuyerAccessLink.objects.filter(pk=link.pk).update(
        created_at=past, expires_at=past + timedelta(hours=72)
    )


def deactivate_primary(application: CreditApplication) -> None:
    ApplicationParticipant.objects.filter(
        application=application, role=ParticipantRole.PRIMARY
    ).update(is_active=False)


@pytest.fixture
def other_application(
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
) -> CreditApplication:
    return make_application(make_opportunity(make_client(document_number="52000111")))


# --- Consumo ----------------------------------------------------------------------------


def test_consume_opens_a_session_and_sets_the_cookie(
    api_client: APIClient, make_link: LinkFactory, application: CreditApplication
) -> None:
    token = generate_opaque_token()
    link = make_link(token_hash=hash_token(token))

    response = consume(api_client, token, HTTP_USER_AGENT="Navegador/1.0")

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"buyer", "application", "session_expires_at"}
    assert body["buyer"] == {"display_name": "Laura Gómez Vélez"}
    assert body["application"] == {
        "id": str(application.pk),
        "code": application.code,
        "public_status": ApplicationStatus.DRAFT,
        "public_status_label": "Borrador",
        "is_editable": True,
        "is_closed": False,
    }
    assert response["Cache-Control"] == "no-store"

    link.refresh_from_db()
    assert link.consumed_at is not None
    session = BuyerSession.objects.get(access_link=link)
    assert session.client_id == link.client_id
    assert session.application_id == application.pk
    assert session.expires_at == link.consumed_at + settings.BUYER_SESSION_LIFETIME
    assert session.last_seen_at == link.consumed_at
    assert session.ip_address == "127.0.0.1"
    assert session.user_agent_summary == "Navegador/1.0"

    cookie = response.cookies[buyer_session_cookie_name()]
    assert buyer_session_cookie_name() == "__Host-buyer_session"
    assert session.session_token_hash == hash_token(cookie.value)
    assert cookie.value != token
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/"
    assert abs(int(cookie["max-age"]) - 24 * 3600) <= 5
    # Token CSRF nuevo para la sesión.
    assert response.cookies[settings.CSRF_COOKIE_NAME].value


def test_consume_rotates_the_csrf_token(api_client: APIClient, make_link: LinkFactory) -> None:
    api_client.get(SESSION_URL)  # Sin sesión todavía.
    api_client.cookies[settings.CSRF_COOKIE_NAME] = "a" * 32
    before = csrf_token(api_client)

    consume(api_client, pending_token(make_link))

    assert csrf_token(api_client) != before


@pytest.mark.parametrize(
    "token",
    ["desconocido-pero-bien-formado-0123456789", "corto", "x" * 200, "con espacios y !"],
)
def test_unknown_or_malformed_token_is_invalid(api_client: APIClient, token: str) -> None:
    assert_error(consume(api_client, token), 401, "MAGIC_LINK_INVALID")
    assert not BuyerSession.objects.exists()


@pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": "abc", "client_id": "x"}])
def test_consume_rejects_an_invalid_body(api_client: APIClient, payload: dict[str, Any]) -> None:
    assert_error(api_client.post(CONSUME_URL, payload), 400, "VALIDATION_ERROR")


def test_expired_link(api_client: APIClient, make_link: LinkFactory) -> None:
    token = generate_opaque_token()
    expire_link(make_link(token_hash=hash_token(token)))

    assert_error(consume(api_client, token), 401, "MAGIC_LINK_EXPIRED")
    assert not BuyerSession.objects.exists()


def test_revoked_link(api_client: APIClient, make_link: LinkFactory) -> None:
    token = pending_token(make_link, revoked_at=timezone.now())

    assert_error(consume(api_client, token), 401, "MAGIC_LINK_REVOKED")


def test_link_is_single_use(api_client: APIClient, make_link: LinkFactory) -> None:
    token = pending_token(make_link)
    assert consume(api_client, token).status_code == 200

    assert_error(consume(APIClient(), token), 401, "MAGIC_LINK_CONSUMED")
    assert BuyerSession.objects.count() == 1


def test_consume_locks_the_link_row(api_client: APIClient, make_link: LinkFactory) -> None:
    """De dos consumos simultáneos, el segundo espera al primero y ve el enlace usado."""
    token = pending_token(make_link)

    with CaptureQueriesContext(connection) as queries:
        assert consume(api_client, token).status_code == 200

    lookups = [q["sql"] for q in queries if 'FROM "buyer_access_links"' in q["sql"]]
    assert lookups
    assert "FOR UPDATE" in lookups[0]


@pytest.mark.parametrize("status", [ApplicationStatus.CANCELLED, ApplicationStatus.WITHDRAWN])
def test_link_of_a_closed_application_is_invalid_and_not_consumed(
    api_client: APIClient,
    make_link: LinkFactory,
    application: CreditApplication,
    status: str,
) -> None:
    token = generate_opaque_token()
    link = make_link(token_hash=hash_token(token))
    set_status(application, status)

    assert_error(consume(api_client, token), 401, "MAGIC_LINK_INVALID")
    link.refresh_from_db()
    assert link.consumed_at is None


def test_link_of_a_former_primary_is_invalid_and_not_consumed(
    api_client: APIClient, make_link: LinkFactory, application: CreditApplication
) -> None:
    token = generate_opaque_token()
    link = make_link(token_hash=hash_token(token))
    deactivate_primary(application)

    assert_error(consume(api_client, token), 401, "MAGIC_LINK_INVALID")
    link.refresh_from_db()
    assert link.consumed_at is None


def test_consume_after_filed_is_allowed(
    api_client: APIClient, make_link: LinkFactory, application: CreditApplication
) -> None:
    token = pending_token(make_link)
    set_status(application, ApplicationStatus.FILED)

    response = consume(api_client, token)

    assert response.status_code == 200
    assert response.json()["application"]["is_editable"] is False


def test_consume_closes_the_other_sessions_of_the_buyer(
    api_client: APIClient,
    make_link: LinkFactory,
    make_session: Callable[..., BuyerSession],
    other_application: CreditApplication,
) -> None:
    previous = make_session()
    elsewhere = make_session(
        access_link=make_link(
            application=other_application,
            client=other_application.opportunity.client,
            consumed_at=timezone.now(),
        )
    )

    consume(api_client, pending_token(make_link))

    previous.refresh_from_db()
    elsewhere.refresh_from_db()
    assert previous.revoked_at is not None
    assert elsewhere.revoked_at is None
    assert BuyerSession.objects.filter(revoked_at__isnull=True).count() == 2


def test_consume_rate_limit_is_per_ip(api_client: APIClient) -> None:
    for _ in range(5):
        assert_error(
            consume(api_client, "x" * 43, REMOTE_ADDR="203.0.113.7"), 401, "MAGIC_LINK_INVALID"
        )

    response = consume(api_client, "x" * 43, REMOTE_ADDR="203.0.113.7")

    assert_error(response, 429, "RATE_LIMITED")
    assert int(response["Retry-After"]) > 0
    # Otra IP no queda bloqueada.
    assert_error(
        consume(api_client, "x" * 43, REMOTE_ADDR="203.0.113.8"), 401, "MAGIC_LINK_INVALID"
    )


def test_tokens_are_never_logged(
    api_client: APIClient, make_link: LinkFactory, caplog: pytest.LogCaptureFixture
) -> None:
    token = pending_token(make_link)

    with caplog.at_level(logging.DEBUG):
        consume(api_client, token)
        raw_session_token = session_token(api_client)
        api_client.get(SESSION_URL)
        api_client.post(LOGOUT_URL)

    assert caplog.records, "se esperaba al menos el registro del consumo"
    for secret in (token, hash_token(token), raw_session_token, hash_token(raw_session_token)):
        assert secret not in caplog.text


def test_a_stale_buyer_cookie_does_not_block_consume(
    buyer_client: APIClient, make_link: LinkFactory
) -> None:
    BuyerSession.objects.update(revoked_at=timezone.now())

    assert consume(buyer_client, pending_token(make_link)).status_code == 200


# --- Sesión -----------------------------------------------------------------------------


def test_session_returns_the_buyer_and_the_application(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    session = BuyerSession.objects.get(revoked_at__isnull=True)

    response = buyer_client.get(SESSION_URL)

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"session", "buyer", "application", "pending_consents"}
    assert body["pending_consents"] == ["DATA_PROCESSING"]
    assert set(body["session"]) == {"id", "created_at", "expires_at"}
    assert body["session"]["id"] == str(session.pk)
    assert body["buyer"] == {"display_name": "Laura Gómez Vélez"}
    assert body["application"]["id"] == str(application.pk)
    assert response["Cache-Control"] == "no-store"


def test_session_without_cookie_is_not_authenticated(api_client: APIClient) -> None:
    assert_error(api_client.get(SESSION_URL), 401, "NOT_AUTHENTICATED")


@pytest.mark.parametrize("value", [generate_opaque_token(), "corto", "con espacios y !"])
def test_unknown_or_malformed_session_cookie_is_expired(api_client: APIClient, value: str) -> None:
    api_client.cookies[buyer_session_cookie_name()] = value

    response = api_client.get(SESSION_URL)

    assert_error(response, 401, "SESSION_EXPIRED")
    assert cookie_was_cleared(response, buyer_session_cookie_name())


@pytest.mark.parametrize("change", ["revoked", "expired", "former_primary"])
def test_session_stops_working(
    buyer_client: APIClient, application: CreditApplication, change: str
) -> None:
    session = BuyerSession.objects.get(revoked_at__isnull=True)
    if change == "revoked":
        BuyerSession.objects.filter(pk=session.pk).update(revoked_at=timezone.now())
    elif change == "expired":
        past = timezone.now() - timedelta(days=2)
        BuyerSession.objects.filter(pk=session.pk).update(
            created_at=past, expires_at=past + timedelta(hours=24)
        )
    else:
        deactivate_primary(application)

    response = buyer_client.get(SESSION_URL)

    assert_error(response, 401, "SESSION_EXPIRED")
    assert cookie_was_cleared(response, buyer_session_cookie_name())


def test_revoking_the_link_from_the_backoffice_ends_the_session(
    buyer_client: APIClient, advisor_client: APIClient
) -> None:
    link = BuyerAccessLink.objects.get(consumed_at__isnull=False)

    assert advisor_client.delete(f"/api/v1/buyer-access-links/{link.pk}").status_code == 204

    assert_error(buyer_client.get(SESSION_URL), 401, "SESSION_EXPIRED")


def test_session_of_a_closed_application_stays_readable(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.WITHDRAWN)

    response = buyer_client.get(SESSION_URL)

    assert response.status_code == 200
    assert response.json()["application"]["is_closed"] is True
    assert buyer_client.get(buyer_application_url(application)).status_code == 200


def test_last_seen_is_written_at_most_once_a_minute(buyer_client: APIClient) -> None:
    session = BuyerSession.objects.get(revoked_at__isnull=True)
    recent = timezone.now() - timedelta(seconds=30)
    BuyerSession.objects.filter(pk=session.pk).update(last_seen_at=recent)

    buyer_client.get(SESSION_URL)
    session.refresh_from_db()
    assert session.last_seen_at == recent

    old = timezone.now() - timedelta(minutes=2)
    BuyerSession.objects.filter(pk=session.pk).update(last_seen_at=old)

    buyer_client.get(SESSION_URL)
    session.refresh_from_db()
    assert session.last_seen_at is not None
    assert session.last_seen_at > old


# --- CSRF y separación de credenciales --------------------------------------------------


def test_buyer_writes_require_csrf(buyer_csrf_client: APIClient) -> None:
    # El `POST` a una ruta de lectura muestra que la autenticación exige CSRF antes
    # de los permisos y de la vista.
    assert_error(buyer_csrf_client.post(SESSION_URL), 403, "CSRF_FAILED")

    response = buyer_csrf_client.post(SESSION_URL, HTTP_X_CSRFTOKEN=csrf_token(buyer_csrf_client))

    # Con CSRF pasa al permiso de consentimientos (Parte 4).
    assert_error(response, 403, "CONSENT_REQUIRED")


def test_buyer_cookie_does_not_open_internal_endpoints(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    assert_error(buyer_client.get("/api/v1/auth/me"), 401, "NOT_AUTHENTICATED")
    assert_error(buyer_client.get(application_url(application)), 401, "NOT_AUTHENTICATED")


def test_internal_session_does_not_open_buyer_endpoints(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    assert_error(advisor_client.get(SESSION_URL), 401, "NOT_AUTHENTICATED")
    assert_error(advisor_client.get(buyer_application_url(application)), 401, "NOT_AUTHENTICATED")


# --- Logout -----------------------------------------------------------------------------


def test_logout_requires_csrf(buyer_csrf_client: APIClient) -> None:
    assert_error(buyer_csrf_client.post(LOGOUT_URL), 403, "CSRF_FAILED")
    assert BuyerSession.objects.filter(revoked_at__isnull=True).exists()


def test_logout_revokes_the_session_and_clears_the_cookie(buyer_csrf_client: APIClient) -> None:
    response = buyer_csrf_client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=csrf_token(buyer_csrf_client))

    assert response.status_code == 204
    assert cookie_was_cleared(response, buyer_session_cookie_name())
    assert not BuyerSession.objects.filter(revoked_at__isnull=True).exists()


def test_logout_after_logout_and_without_cookie(buyer_client: APIClient) -> None:
    token = session_token(buyer_client)
    assert buyer_client.post(LOGOUT_URL).status_code == 204

    buyer_client.cookies[buyer_session_cookie_name()] = token
    assert_error(buyer_client.get(SESSION_URL), 401, "SESSION_EXPIRED")
    buyer_client.cookies[buyer_session_cookie_name()] = token
    assert buyer_client.post(LOGOUT_URL).status_code == 204
    assert APIClient().post(LOGOUT_URL).status_code == 204


# --- Proceso y solicitud ----------------------------------------------------------------


def test_processes_lists_only_the_session_application(
    buyer_client: APIClient,
    application: CreditApplication,
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    buyer: Client,
) -> None:
    set_status(application, ApplicationStatus.CANCELLED)
    make_application(make_opportunity(buyer))  # Otro intento del mismo comprador.

    response = buyer_client.get(PROCESSES_URL)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 1
    [process] = body["items"]
    assert set(process) == {
        "id",
        "code",
        "public_status",
        "public_status_label",
        "is_editable",
        "is_closed",
        "purpose",
        "next_action",
        "progress_percentage",
        "created_at",
        "updated_at",
    }
    assert process["id"] == str(application.pk)
    assert process["public_status"] == ApplicationStatus.CANCELLED
    assert process["next_action"] == "La solicitud fue cancelada."
    assert process["purpose"] == {"code": "PURCHASE_NEW", "label": "Compra de vivienda nueva"}


def test_application_detail_is_the_portal_dto(
    buyer_client: APIClient,
    application: CreditApplication,
    make_client: Callable[..., Client],
) -> None:
    co_applicant = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80999111", first_names="Pedro"),
        role=ParticipantRole.CO_APPLICANT,
    )
    ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80999222", first_names="Inactivo"),
        role=ParticipantRole.SOLIDARY_DEBTOR,
        is_active=False,
    )

    response = buyer_client.get(buyer_application_url(application))

    assert response.status_code == 200, response.content
    assert response["ETag"] == f'"{application.version}"'
    body = response.json()
    assert set(body) == {
        "id",
        "code",
        "public_status",
        "public_status_label",
        "is_editable",
        "is_closed",
        "purpose",
        "next_action",
        "progress_percentage",
        "created_at",
        "updated_at",
        "version",
        "progress",
        "participants",
        "property",
        "financing",
    }
    assert body["next_action"] == "Tu asesor está preparando la solicitud."
    assert body["property"] is None
    assert body["financing"] is None
    assert [p["role"] for p in body["participants"]] == ["PRIMARY", "CO_APPLICANT"]
    assert body["participants"][1] == {
        "id": str(co_applicant.pk),
        "role": "CO_APPLICANT",
        "role_label": "Co-solicitante",
        "full_name": "Pedro Gómez Vélez",
        "contributes_income": True,
    }
    progress = body["progress"]
    assert progress["percentage"] == body["progress_percentage"]
    codes = [item["code"] for item in progress["items"]]
    assert "bank_evaluation" not in codes
    assert set(progress["items"][0]) == {"code", "complete", "message", "participant_id"}


def test_application_detail_with_property_and_financing(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    Property.objects.create(
        application=application,
        property_type_item=catalog_item("property_type", "APARTMENT"),
        condition_item=catalog_item("property_condition", "NEW"),
        city_item=catalog_item("municipality", "11001"),
        estimated_value_cop=420_000_000,
        ownership_notes="Nota interna del asesor",
    )
    FinancingPreference.objects.create(
        application=application,
        financing_mode_item=catalog_item("financing_mode", "BANK_CREDIT"),
        requested_amount_cop=294_000_000,
        term_months=240,
    )

    body = buyer_client.get(buyer_application_url(application)).json()

    assert body["property"]["estimated_value_cop"] == 420_000_000
    assert body["property"]["city"]["code"] == "11001"
    assert "ownership_notes" not in body["property"]
    assert body["financing"]["financing_mode"]["code"] == "BANK_CREDIT"
    assert body["financing"]["bank_product"] is None
    assert body["financing"]["requested_amount_cop"] == 294_000_000


def test_another_application_is_not_found(
    buyer_client: APIClient, other_application: CreditApplication
) -> None:
    assert_error(
        buyer_client.get(buyer_application_url(other_application)), 404, "RESOURCE_NOT_FOUND"
    )
    assert_error(buyer_client.get(buyer_application_url(uuid.uuid4())), 404, "RESOURCE_NOT_FOUND")


def test_every_status_has_a_next_action_and_a_catalog_label() -> None:
    for status in ApplicationStatus.values:
        assert buyer_portal.next_action(status)
        assert buyer_portal.public_status_label(status) == ApplicationStatus(status).label


def test_public_status_label_falls_back_without_catalog_item() -> None:
    from apps.catalogs.models import CatalogItem

    CatalogItem.objects.filter(catalog__code="application_status", code="DRAFT").delete()

    assert buyer_portal.public_status_label(ApplicationStatus.DRAFT) == "Borrador"
