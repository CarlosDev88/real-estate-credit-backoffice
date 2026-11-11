"""Consentimientos del comprador y bloqueo de escrituras (decisión 16, Parte 4)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity import consents
from apps.identity.models import BuyerSession, ConsentAction, ConsentDefinition, ConsentRecord
from tests.applications.conftest import application_url
from tests.helpers import assert_error, csrf_token

pytestmark = pytest.mark.django_db

SESSION_URL = "/api/v1/buyer/session"
LOGOUT_URL = "/api/v1/buyer/session/logout"
# Marca de los casos que usan la definición sembrada, que no existe al parametrizar.
SEEDED = "seeded"


def consents_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/consents"


def definition(code: str) -> ConsentDefinition:
    return ConsentDefinition.objects.get(code=code, version=1)


def post_consent(
    client: APIClient,
    application: CreditApplication,
    consent: ConsentDefinition,
    action: str = ConsentAction.ACCEPTED,
    **extra: Any,
) -> Any:
    payload = {"consent_definition_id": str(consent.pk), "action": action}
    return client.post(consents_url(application), payload, **extra)


def accept(client: APIClient, application: CreditApplication, code: str) -> None:
    assert post_consent(client, application, definition(code)).status_code == 201


def by_code(response: Any) -> dict[str, dict[str, Any]]:
    return {item["code"]: item for item in response.json()["items"]}


@pytest.fixture
def add_participant(
    application: CreditApplication, make_client: Callable[..., Client]
) -> Callable[..., ApplicationParticipant]:
    def _add(role: str = ParticipantRole.CO_APPLICANT, **extra: Any) -> ApplicationParticipant:
        client = make_client(document_number=f"80{ApplicationParticipant.objects.count():06d}")
        return ApplicationParticipant.objects.create(
            application=application, client=client, role=role, **extra
        )

    return _add


@pytest.fixture
def other_application(
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
) -> CreditApplication:
    return make_application(make_opportunity(make_client(document_number="52000111")))


# --- Listado ----------------------------------------------------------------------------


def test_lists_the_effective_consents_and_what_is_required(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    response = buyer_client.get(consents_url(application))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["pending_required"] == ["DATA_PROCESSING"]
    items = by_code(response)
    assert list(items) == ["CO_APPLICANT_AUTHORIZATION", "DATA_PROCESSING"]
    data_processing = items["DATA_PROCESSING"]
    seeded = definition("DATA_PROCESSING")
    assert data_processing == {
        "id": str(seeded.pk),
        "code": "DATA_PROCESSING",
        "version": 1,
        "title": seeded.title,
        "body": seeded.body,
        "content_hash": seeded.content_hash,
        "effective_from": data_processing["effective_from"],
        "required": True,
        "status": "PENDING",
        "accepted_at": None,
    }
    assert items["CO_APPLICANT_AUTHORIZATION"]["required"] is False


@pytest.mark.parametrize(
    ("role", "is_active", "required"),
    [
        (ParticipantRole.CO_APPLICANT, True, True),
        (ParticipantRole.SOLIDARY_DEBTOR, True, True),
        (ParticipantRole.CO_APPLICANT, False, False),
    ],
)
def test_co_applicant_authorization_is_required_with_active_co_applicants(
    buyer_client: APIClient,
    application: CreditApplication,
    add_participant: Callable[..., ApplicationParticipant],
    role: str,
    is_active: bool,
    required: bool,
) -> None:
    add_participant(role, is_active=is_active)

    response = buyer_client.get(consents_url(application))

    assert by_code(response)["CO_APPLICANT_AUTHORIZATION"]["required"] is required
    assert ("CO_APPLICANT_AUTHORIZATION" in response.json()["pending_required"]) is required


def test_only_the_highest_effective_version_is_listed() -> None:
    now = timezone.now()
    v2 = ConsentDefinition.objects.create(
        code="DATA_PROCESSING", version=2, title="v2", body="Texto 2", effective_from=now
    )
    ConsentDefinition.objects.create(
        code="DATA_PROCESSING",
        version=3,
        title="v3",
        body="Texto 3",
        effective_from=now + timedelta(days=1),
    )
    retiring = definition("CO_APPLICANT_AUTHORIZATION")
    ConsentDefinition.objects.filter(pk=retiring.pk).update(retired_at=now + timedelta(days=1))

    effective = consents.effective_definitions()

    assert [d.pk for d in effective] == [retiring.pk, v2.pk]

    ConsentDefinition.objects.filter(pk=retiring.pk).update(retired_at=now)
    assert [d.pk for d in consents.effective_definitions()] == [v2.pk]


def test_another_application_is_not_found(
    buyer_client: APIClient, other_application: CreditApplication
) -> None:
    assert_error(buyer_client.get(consents_url(other_application)), 404, "RESOURCE_NOT_FOUND")
    response = post_consent(buyer_client, other_application, definition("DATA_PROCESSING"))
    assert_error(response, 404, "RESOURCE_NOT_FOUND")
    assert not ConsentRecord.objects.exists()


# --- Aceptación y retiro ----------------------------------------------------------------


def test_accept_records_the_evidence(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    consent = definition("DATA_PROCESSING")

    response = post_consent(buyer_client, application, consent, HTTP_USER_AGENT="Navegador/2.0")

    assert response.status_code == 201, response.content
    record = ConsentRecord.objects.get()
    session = BuyerSession.objects.get(revoked_at__isnull=True)
    assert response.json() == {
        "id": str(record.pk),
        "consent_definition_id": str(consent.pk),
        "code": "DATA_PROCESSING",
        "version": 1,
        "action": "ACCEPTED",
        "created_at": response.json()["created_at"],
    }
    assert record.client_id == session.client_id
    assert record.user_id is None
    assert record.application_id == application.pk
    assert record.buyer_session_id == session.pk
    assert record.ip_address == "127.0.0.1"
    assert record.user_agent_summary == "Navegador/2.0"

    listed = buyer_client.get(consents_url(application))
    assert by_code(listed)["DATA_PROCESSING"]["status"] == "ACCEPTED"
    assert by_code(listed)["DATA_PROCESSING"]["accepted_at"] is not None
    assert listed.json()["pending_required"] == []
    assert buyer_client.get(SESSION_URL).json()["pending_consents"] == []


def test_accepting_twice_returns_the_existing_record(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    consent = definition("DATA_PROCESSING")
    first = post_consent(buyer_client, application, consent)

    second = post_consent(buyer_client, application, consent)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert ConsentRecord.objects.count() == 1


def test_withdrawal_is_a_new_record_and_leaves_the_consent_pending(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    consent = definition("DATA_PROCESSING")
    post_consent(buyer_client, application, consent)

    response = post_consent(buyer_client, application, consent, ConsentAction.WITHDRAWN)

    assert response.status_code == 201
    assert response.json()["action"] == "WITHDRAWN"
    assert ConsentRecord.objects.count() == 2
    listed = buyer_client.get(consents_url(application))
    assert by_code(listed)["DATA_PROCESSING"]["status"] == "WITHDRAWN"
    assert by_code(listed)["DATA_PROCESSING"]["accepted_at"] is None
    assert listed.json()["pending_required"] == ["DATA_PROCESSING"]

    again = post_consent(buyer_client, application, consent, ConsentAction.WITHDRAWN)
    assert again.status_code == 200
    assert again.json()["id"] == response.json()["id"]

    # Volver a aceptar después de retirar es otra fila.
    assert post_consent(buyer_client, application, consent).status_code == 201
    assert ConsentRecord.objects.count() == 3


def test_withdrawing_what_was_never_accepted(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    response = post_consent(
        buyer_client, application, definition("DATA_PROCESSING"), ConsentAction.WITHDRAWN
    )

    assert_error(response, 409, "CONSENT_NOT_ACCEPTED")
    assert not ConsentRecord.objects.exists()


@pytest.mark.parametrize("case", ["future", "retired", "superseded"])
def test_a_version_that_is_not_effective_cannot_be_used(
    buyer_client: APIClient, application: CreditApplication, case: str
) -> None:
    now = timezone.now()
    target = definition("DATA_PROCESSING")
    if case == "future":
        target = ConsentDefinition.objects.create(
            code="DATA_PROCESSING",
            version=2,
            title="v2",
            body="Texto 2",
            effective_from=now + timedelta(days=1),
        )
    elif case == "retired":
        ConsentDefinition.objects.filter(pk=target.pk).update(retired_at=now)
    else:
        ConsentDefinition.objects.create(
            code="DATA_PROCESSING", version=2, title="v2", body="Texto 2", effective_from=now
        )

    response = post_consent(buyer_client, application, target)

    assert_error(response, 422, "CONSENT_NOT_EFFECTIVE")
    assert not ConsentRecord.objects.exists()


def test_a_new_version_leaves_the_consent_pending_again(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    accept(buyer_client, application, "DATA_PROCESSING")
    v2 = ConsentDefinition.objects.create(
        code="DATA_PROCESSING", version=2, title="v2", body="Texto 2", effective_from=timezone.now()
    )

    listed = buyer_client.get(consents_url(application))

    assert by_code(listed)["DATA_PROCESSING"]["id"] == str(v2.pk)
    assert by_code(listed)["DATA_PROCESSING"]["status"] == "PENDING"
    assert listed.json()["pending_required"] == ["DATA_PROCESSING"]


@pytest.mark.parametrize(
    "payload",
    [
        {"consent_definition_id": "00000000-0000-0000-0000-000000000000", "action": "ACCEPTED"},
        {"consent_definition_id": "no-es-uuid", "action": "ACCEPTED"},
        {"action": "ACCEPTED"},
        {"consent_definition_id": SEEDED, "action": "REJECTED"},
        {"consent_definition_id": SEEDED, "action": "ACCEPTED", "client_id": "x"},
    ],
)
def test_invalid_body(
    buyer_client: APIClient, application: CreditApplication, payload: dict[str, Any]
) -> None:
    if payload.get("consent_definition_id") == SEEDED:
        payload = {**payload, "consent_definition_id": str(definition("DATA_PROCESSING").pk)}

    response = buyer_client.post(consents_url(application), payload)

    assert_error(response, 400, "VALIDATION_ERROR")


def test_closed_application_rejects_consent_changes_but_lists_them(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=ApplicationStatus.WITHDRAWN)

    response = post_consent(buyer_client, application, definition("DATA_PROCESSING"))

    assert_error(response, 409, "APPLICATION_CLOSED")
    assert buyer_client.get(consents_url(application)).status_code == 200


def test_consent_actions_lock_the_session(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    with CaptureQueriesContext(connection) as queries:
        accept(buyer_client, application, "DATA_PROCESSING")

    locks = [q["sql"] for q in queries if 'FROM "buyer_sessions"' in q["sql"]]
    assert any("FOR UPDATE" in sql for sql in locks)


def test_consent_actions_require_csrf(
    buyer_csrf_client: APIClient, application: CreditApplication
) -> None:
    consent = definition("DATA_PROCESSING")
    assert_error(post_consent(buyer_csrf_client, application, consent), 403, "CSRF_FAILED")

    response = post_consent(
        buyer_csrf_client,
        application,
        consent,
        HTTP_X_CSRFTOKEN=csrf_token(buyer_csrf_client),
    )

    assert response.status_code == 201


# --- Bloqueo de escrituras --------------------------------------------------------------


def test_pending_consents_block_buyer_writes(
    buyer_client: APIClient,
    application: CreditApplication,
    add_participant: Callable[..., ApplicationParticipant],
) -> None:
    add_participant()
    # Ninguna escritura del portal existe todavía fuera de los consentimientos: el
    # `POST` a una ruta de lectura llega al permiso antes de responder `405`.
    body = assert_error(buyer_client.post(SESSION_URL), 403, "CONSENT_REQUIRED")
    assert [d["code"] for d in body["details"]] == ["CO_APPLICANT_AUTHORIZATION", "DATA_PROCESSING"]
    assert body["details"][1]["resource_id"] == str(definition("DATA_PROCESSING").pk)

    accept(buyer_client, application, "DATA_PROCESSING")
    body = assert_error(buyer_client.post(SESSION_URL), 403, "CONSENT_REQUIRED")
    assert [d["code"] for d in body["details"]] == ["CO_APPLICANT_AUTHORIZATION"]

    accept(buyer_client, application, "CO_APPLICANT_AUTHORIZATION")
    assert_error(buyer_client.post(SESSION_URL), 405, "METHOD_NOT_ALLOWED")


def test_reads_and_logout_are_allowed_with_pending_consents(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    assert buyer_client.get(SESSION_URL).status_code == 200
    assert buyer_client.get(f"/api/v1/buyer/applications/{application.pk}").status_code == 200
    assert buyer_client.get("/api/v1/buyer/processes").status_code == 200
    assert buyer_client.post(LOGOUT_URL).status_code == 204


def test_acceptance_in_another_application_does_not_count(
    buyer_client: APIClient,
    application: CreditApplication,
    other_application: CreditApplication,
) -> None:
    ConsentRecord.objects.create(
        consent_definition=definition("DATA_PROCESSING"),
        client=other_application.opportunity.client,
        application=other_application,
        action=ConsentAction.ACCEPTED,
    )

    assert buyer_client.get(SESSION_URL).json()["pending_consents"] == ["DATA_PROCESSING"]


# --- Evidencias para el backoffice ------------------------------------------------------


def internal_url(application: CreditApplication) -> str:
    return application_url(application, "/consents")


def test_advisor_lists_the_evidence(
    buyer_client: APIClient, advisor_client: APIClient, application: CreditApplication
) -> None:
    consent = definition("DATA_PROCESSING")
    post_consent(buyer_client, application, consent)
    post_consent(buyer_client, application, consent, ConsentAction.WITHDRAWN)

    response = advisor_client.get(internal_url(application))

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 2
    latest = body["items"][0]
    session = BuyerSession.objects.get(revoked_at__isnull=True)
    assert set(latest) == {
        "id",
        "consent_definition",
        "client",
        "user",
        "action",
        "ip_address",
        "user_agent_summary",
        "buyer_session_id",
        "created_at",
    }
    assert latest["action"] == "WITHDRAWN"
    assert body["items"][1]["action"] == "ACCEPTED"
    assert latest["consent_definition"] == {
        "id": str(consent.pk),
        "code": "DATA_PROCESSING",
        "version": 1,
        "title": consent.title,
        "content_hash": consent.content_hash,
    }
    assert latest["client"] == {
        "id": str(application.opportunity.client_id),
        "full_name": "Laura Gómez Vélez",
    }
    assert latest["user"] is None
    assert latest["ip_address"] == "127.0.0.1"
    assert latest["buyer_session_id"] == str(session.pk)


def test_admin_sees_the_evidence(admin_client: APIClient, application: CreditApplication) -> None:
    response = admin_client.get(internal_url(application))

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_evidence_out_of_scope_or_without_permission(
    other_advisor_client: APIClient,
    broker_client: APIClient,
    partner_client: APIClient,
    api_client: APIClient,
    buyer_client: APIClient,
    application: CreditApplication,
) -> None:
    url = internal_url(application)
    assert_error(other_advisor_client.get(url), 404, "RESOURCE_NOT_FOUND")
    assert_error(broker_client.get(url), 403, "PERMISSION_DENIED")
    assert_error(partner_client.get(url), 403, "PERMISSION_DENIED")
    assert_error(api_client.get(url), 401, "NOT_AUTHENTICATED")
    assert_error(buyer_client.get(url), 401, "NOT_AUTHENTICATED")
