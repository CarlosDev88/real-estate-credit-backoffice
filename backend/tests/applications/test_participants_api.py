"""Participantes de la solicitud (API §17.1) y su visibilidad en CRM."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from django.dispatch import Signal
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.applications import services
from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.applications.signals import application_updated, participant_added, participant_removed
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from tests.applications.conftest import application_url
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PARTICIPANTS_URL = "/api/v1/application-participants"
CLIENTS_URL = "/api/v1/clients"

NEW_CLIENT: dict[str, Any] = {
    "document_type_code": "CC",
    "document_number": "1015.882.421",
    "first_names": "Mateo",
    "last_names": "Vargas León",
    "phone": "+573001112233",
}


def participant_url(participant: ApplicationParticipant | str) -> str:
    participant_id = participant if isinstance(participant, str) else participant.id
    return f"{PARTICIPANTS_URL}/{participant_id}"


def add(client: APIClient, application: CreditApplication, **payload: Any) -> Any:
    payload.setdefault("role_code", "CO_APPLICANT")
    return client.post(application_url(application, "/participants"), payload, format="json")


def patch(
    client: APIClient,
    participant: ApplicationParticipant,
    data: dict[str, Any],
    if_match: str | None = '"1"',
) -> Any:
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.patch(participant_url(participant), data, format="json", headers=headers)


def version_of(application: CreditApplication) -> int:
    application.refresh_from_db(fields=["version"])
    return application.version


@contextmanager
def capture(
    signal: Signal, django_capture_on_commit_callbacks: Any
) -> Iterator[list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    def receiver(**kwargs: Any) -> None:
        received.append(kwargs)

    signal.connect(receiver)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            yield received
    finally:
        signal.disconnect(receiver)


@pytest.fixture
def other_client(make_client: Callable[..., Client], admin_user: User) -> Client:
    """Cliente que el asesor no ve por CRM: lo creó el administrador, sin oportunidad."""
    return make_client(
        document_number="80123456", first_names="Mateo", last_names="Vargas", created_by=admin_user
    )


@pytest.fixture
def co_applicant(application: CreditApplication, other_client: Client) -> ApplicationParticipant:
    return ApplicationParticipant.objects.create(
        application=application, client=other_client, role=ParticipantRole.CO_APPLICANT
    )


# --- Lista y alcance --------------------------------------------------------------------


def test_list_shows_active_participants_with_etag(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    co_applicant: ApplicationParticipant,
) -> None:
    co_applicant.is_active = False
    co_applicant.save()

    response = advisor_client.get(application_url(application, "/participants"))

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"1"'
    [row] = response.json()["items"]
    assert row["id"] == str(primary.id)
    assert row["role"] == "PRIMARY"
    assert row["is_active"] is True
    assert row["client"]["full_name"] == "Laura Gómez Vélez"
    assert row["financial_profile_id"] is None


def test_list_can_include_retired_participants(
    admin_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    co_applicant.is_active = False
    co_applicant.save()

    response = admin_client.get(
        application_url(application, "/participants"), {"include_inactive": "true"}
    )

    assert response.status_code == 200
    assert [row["is_active"] for row in response.json()["items"]] == [True, False]
    invalid = admin_client.get(
        application_url(application, "/participants"), {"include_inactive": "talvez"}
    )
    assert_error(invalid, 400, "VALIDATION_ERROR")


def test_broker_and_partner_never_see_participants(
    broker_client: APIClient,
    partner_client: APIClient,
    broker_user: User,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    opportunity = application.opportunity
    opportunity.origin_user = broker_user
    opportunity.save()

    for http in (broker_client, partner_client):
        assert_error(
            http.get(application_url(application, "/participants")), 403, "PERMISSION_DENIED"
        )
        assert_error(http.get(participant_url(co_applicant)), 403, "PERMISSION_DENIED")
        assert_error(
            add(http, application, client_id=str(co_applicant.client_id)), 403, "PERMISSION_DENIED"
        )


def test_participants_out_of_scope_are_not_found(
    other_advisor_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    assert_error(
        other_advisor_client.get(application_url(application, "/participants")),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error(other_advisor_client.get(participant_url(co_applicant)), 404, "RESOURCE_NOT_FOUND")
    assert_error(
        patch(other_advisor_client, co_applicant, {"contributes_income": False}),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error(
        other_advisor_client.delete(participant_url(co_applicant)), 404, "RESOURCE_NOT_FOUND"
    )


# --- Alta ------------------------------------------------------------------------------


def test_add_visible_client_bumps_version_and_notifies(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    make_client: Callable[..., Client],
    django_capture_on_commit_callbacks: Any,
) -> None:
    spouse = make_client(document_number="52111222", first_names="Ana", created_by=advisor_user)

    with capture(participant_added, django_capture_on_commit_callbacks) as received:
        response = add(
            advisor_client,
            application,
            client_id=str(spouse.id),
            role_code="SOLIDARY_DEBTOR",
            income_share_cop=2_500_000,
        )

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["application_id"] == str(application.id)
    assert body["client"]["id"] == str(spouse.id)
    assert body["role"] == "SOLIDARY_DEBTOR"
    assert body["contributes_income"] is True
    assert body["income_share_cop"] == 2_500_000
    assert version_of(application) == 2
    [event] = received
    assert event["participant"].id == ApplicationParticipant.objects.get(client=spouse).id
    assert event["reactivated"] is False
    assert event["actor"] == advisor_user


def test_add_with_identity_creates_the_client(
    advisor_client: APIClient, advisor_user: User, application: CreditApplication
) -> None:
    response = add(advisor_client, application, contributes_income=False, **NEW_CLIENT)

    assert response.status_code == 201, response.content
    client = Client.objects.get(document_number="1015882421")
    assert client.created_by == advisor_user
    assert client.phone == "+573001112233"
    body = response.json()
    assert body["client"]["id"] == str(client.id)
    assert body["contributes_income"] is False
    assert body["income_share_cop"] is None


def test_add_with_an_existing_document_conflicts(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    make_client: Callable[..., Client],
) -> None:
    existing = make_client(document_number="1015882421", created_by=advisor_user)

    response = add(advisor_client, application, **NEW_CLIENT)

    body = assert_error(response, 409, "DUPLICATE_CLIENT_DOCUMENT")
    assert body["details"][0]["resource_id"] == str(existing.id)
    assert application.participants.count() == 1
    assert version_of(application) == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {"role_code": "PRIMARY", "client_id": "00000000-0000-0000-0000-000000000000"},
            "role_code",
        ),
        (
            {"client_id": "00000000-0000-0000-0000-000000000000", "first_names": "Ana"},
            "first_names",
        ),
        ({}, "document_type_code"),
        ({**NEW_CLIENT, "document_number": "12ab"}, "document_number"),
        ({**NEW_CLIENT, "relationship_code": "SPOUSE"}, "relationship_code"),
        ({**NEW_CLIENT, "contributes_income": False, "income_share_cop": 10}, "income_share_cop"),
        ({**NEW_CLIENT, "income_share_cop": -1}, "income_share_cop"),
    ],
)
def test_add_validates_input(
    advisor_client: APIClient, application: CreditApplication, payload: dict[str, Any], field: str
) -> None:
    body = assert_error(add(advisor_client, application, **payload), 400, "VALIDATION_ERROR")

    assert field in {detail["field"] for detail in body["details"]}
    assert not Client.objects.filter(document_number="1015882421").exists()
    assert version_of(application) == 1


def test_add_rejects_invisible_or_repeated_clients(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    other_client: Client,
) -> None:
    invisible = add(advisor_client, application, client_id=str(other_client.id))
    repeated = add(advisor_client, application, client_id=str(primary.client_id))

    for response in (invisible, repeated):
        body = assert_error(response, 400, "VALIDATION_ERROR")
        assert body["details"][0]["field"] == "client_id"
    assert version_of(application) == 1


def test_participants_are_frozen_from_filing(
    admin_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    application.status = ApplicationStatus.FILED
    application.save()

    assert_error(add(admin_client, application, **NEW_CLIENT), 409, "APPLICATION_NOT_EDITABLE")
    assert_error(
        patch(admin_client, co_applicant, {"contributes_income": False}),
        409,
        "APPLICATION_NOT_EDITABLE",
    )
    assert_error(
        admin_client.delete(participant_url(co_applicant)), 409, "APPLICATION_NOT_EDITABLE"
    )
    assert not Client.objects.filter(document_number="1015882421").exists()


def test_readding_a_retired_client_reactivates_the_row(
    admin_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
    django_capture_on_commit_callbacks: Any,
) -> None:
    co_applicant.is_active = False
    co_applicant.save()

    with capture(participant_added, django_capture_on_commit_callbacks) as received:
        response = add(
            admin_client,
            application,
            client_id=str(co_applicant.client_id),
            role_code="SOLIDARY_DEBTOR",
            contributes_income=False,
        )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["id"] == str(co_applicant.id)
    assert body["is_active"] is True
    assert body["role"] == "SOLIDARY_DEBTOR"
    assert body["contributes_income"] is False
    assert received[0]["reactivated"] is True
    assert version_of(application) == 2


# --- Edición ---------------------------------------------------------------------------


def test_patch_requires_a_current_version(
    advisor_client: APIClient, co_applicant: ApplicationParticipant
) -> None:
    assert_error(
        patch(advisor_client, co_applicant, {"contributes_income": False}, if_match=None),
        428,
        "PRECONDITION_REQUIRED",
    )
    stale = patch(advisor_client, co_applicant, {"contributes_income": False}, if_match='"7"')
    body = assert_error(stale, 409, "STALE_VERSION")
    assert body["details"][0]["current_version"] == 1


def test_patch_changes_role_and_income_share(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
    django_capture_on_commit_callbacks: Any,
) -> None:
    with capture(application_updated, django_capture_on_commit_callbacks) as received:
        response = patch(
            advisor_client,
            co_applicant,
            {"role_code": "SOLIDARY_DEBTOR", "income_share_cop": 1_800_000},
        )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["role"] == "SOLIDARY_DEBTOR"
    assert body["income_share_cop"] == 1_800_000
    assert [event["fields"] for event in received] == [["participants"]]
    assert received[0]["actor"] == advisor_user

    same = patch(advisor_client, co_applicant, {"role_code": "SOLIDARY_DEBTOR"}, if_match='"2"')
    assert same.status_code == 200
    assert same["ETag"] == '"2"'


def test_primary_keeps_its_role_but_can_change_income(
    advisor_client: APIClient, primary: ApplicationParticipant
) -> None:
    body = assert_error(
        patch(advisor_client, primary, {"role_code": "CO_APPLICANT"}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "role_code"

    response = patch(advisor_client, primary, {"income_share_cop": 6_000_000})
    assert response.status_code == 200, response.content
    assert response.json()["income_share_cop"] == 6_000_000


def test_income_share_requires_contributing(
    advisor_client: APIClient, co_applicant: ApplicationParticipant
) -> None:
    co_applicant.income_share_cop = 1_000_000
    co_applicant.save()

    response = patch(advisor_client, co_applicant, {"contributes_income": False})

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "income_share_cop"
    ok = patch(
        advisor_client, co_applicant, {"contributes_income": False, "income_share_cop": None}
    )
    assert ok.status_code == 200, ok.content


def test_retired_participants_are_readable_but_not_editable(
    advisor_client: APIClient, co_applicant: ApplicationParticipant
) -> None:
    co_applicant.is_active = False
    co_applicant.save()

    detail = advisor_client.get(participant_url(co_applicant))
    assert detail.status_code == 200
    assert detail.json()["is_active"] is False
    assert detail["ETag"] == '"1"'

    body = assert_error(
        patch(advisor_client, co_applicant, {"contributes_income": False}),
        409,
        "PARTICIPANT_INACTIVE",
    )
    assert "agrégalo de nuevo" in body["message"]


# --- Retiro ----------------------------------------------------------------------------


def test_remove_marks_the_participant_inactive(
    advisor_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
    django_capture_on_commit_callbacks: Any,
) -> None:
    with capture(participant_removed, django_capture_on_commit_callbacks) as received:
        response = advisor_client.delete(participant_url(co_applicant))

    assert response.status_code == 204
    assert response["ETag"] == '"2"'
    co_applicant.refresh_from_db()
    assert co_applicant.is_active is False
    assert [event["participant"].id for event in received] == [co_applicant.id]

    again = advisor_client.delete(participant_url(co_applicant))
    assert again.status_code == 204
    assert again["ETag"] == '"2"'


def test_primary_cannot_be_removed(
    advisor_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    assert_error(advisor_client.delete(participant_url(primary)), 400, "VALIDATION_ERROR")
    primary.refresh_from_db()
    assert primary.is_active is True
    assert version_of(application) == 1


# --- Visibilidad en CRM ----------------------------------------------------------------


def test_advisor_sees_co_applicants_of_assigned_applications(
    advisor_client: APIClient,
    other_advisor_client: APIClient,
    co_applicant: ApplicationParticipant,
) -> None:
    url = f"{CLIENTS_URL}/{co_applicant.client_id}"

    assert advisor_client.get(url).status_code == 200
    assert_error(other_advisor_client.get(url), 404, "RESOURCE_NOT_FOUND")

    co_applicant.is_active = False
    co_applicant.save()
    assert advisor_client.get(url).status_code == 200


def test_broker_does_not_gain_visibility_by_participation(
    broker_client: APIClient,
    broker_user: User,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
    opportunity: Opportunity,
) -> None:
    opportunity.origin_user = broker_user
    opportunity.save()

    response = broker_client.get(f"{CLIENTS_URL}/{co_applicant.client_id}")

    assert_error(response, 404, "RESOURCE_NOT_FOUND")
    assert broker_client.get(f"{CLIENTS_URL}/{opportunity.client_id}").status_code == 200


def test_reassigned_advisor_sees_the_participants(
    other_advisor: User,
    other_advisor_client: APIClient,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    application.assigned_advisor = other_advisor
    application.save()

    response = other_advisor_client.get(CLIENTS_URL)

    assert response.status_code == 200
    assert str(co_applicant.client_id) in {row["id"] for row in response.json()["items"]}


# --- Guardas del servicio (las vistas ya filtran estos casos) --------------------------


def test_service_guards_roles_and_client_source(
    advisor_user: User,
    application: CreditApplication,
    co_applicant: ApplicationParticipant,
) -> None:
    with pytest.raises(ValidationError):
        services.add_participant(
            advisor_user, application, role=ParticipantRole.PRIMARY, client=co_applicant.client
        )
    with pytest.raises(ValueError, match="client_data"):
        services.add_participant(advisor_user, application, role=ParticipantRole.CO_APPLICANT)
    with pytest.raises(ValidationError):
        services.update_participant(
            advisor_user,
            co_applicant,
            expected_version=1,
            changes={"role": ParticipantRole.PRIMARY},
        )
    co_applicant.refresh_from_db()
    assert co_applicant.role == ParticipantRole.CO_APPLICANT
    assert version_of(application) == 1
