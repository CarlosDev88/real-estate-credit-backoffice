"""Perfil financiero y fuentes de ingreso de los participantes (API §17.2)."""

from datetime import date, timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
)
from apps.applications.signals import application_updated
from apps.catalogs.workflow import ApplicationStatus
from apps.identity.models import User
from tests.applications.conftest import catalog_item
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PARTICIPANTS_URL = "/api/v1/application-participants"
PROFILES_URL = "/api/v1/financial-profiles"
SOURCES_URL = "/api/v1/income-sources"

PROFILE: dict[str, Any] = {
    "employment_profile_code": "EMPLOYEE",
    "contract_type_code": "INDEFINITE",
    "employer_name": "Tecnología Andina SAS",
    "employment_start_date": "2022-02-01",
    "monthly_income_cop": 7_800_000,
    "monthly_expenses_cop": 2_450_000,
    "assets_cop": 96_000_000,
    "liabilities_cop": 18_200_000,
    "funds_origin_code": "SALARY",
}
SALARY: dict[str, Any] = {
    "source_type_code": "SALARY",
    "payer_name": "Tecnología Andina SAS",
    "monthly_amount_cop": 7_000_000,
    "is_primary": True,
}


def profile_url(participant: ApplicationParticipant) -> str:
    return f"{PARTICIPANTS_URL}/{participant.id}/financial-profile"


def sources_url(profile: FinancialProfile) -> str:
    return f"{PROFILES_URL}/{profile.id}/income-sources"


def source_url(source: IncomeSource) -> str:
    return f"{SOURCES_URL}/{source.id}"


def put(
    client: APIClient,
    participant: ApplicationParticipant,
    data: dict[str, Any],
    if_match: str | None = '"1"',
) -> Any:
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.put(profile_url(participant), data, format="json", headers=headers)


def patch_source(
    client: APIClient, source: IncomeSource, data: dict[str, Any], if_match: str | None = '"1"'
) -> Any:
    headers = {} if if_match is None else {"If-Match": if_match}
    return client.patch(source_url(source), data, format="json", headers=headers)


def version_of(application: CreditApplication) -> int:
    application.refresh_from_db(fields=["version"])
    return application.version


@pytest.fixture
def profile(primary: ApplicationParticipant) -> FinancialProfile:
    return FinancialProfile.objects.create(
        participant=primary,
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
        monthly_income_cop=7_800_000,
    )


def make_source(
    profile: FinancialProfile, amount: int, *, is_primary: bool = False
) -> IncomeSource:
    return IncomeSource.objects.create(
        financial_profile=profile,
        source_type_item=catalog_item("income_source_type", "SALARY"),
        monthly_amount_cop=amount,
        is_primary=is_primary,
    )


def retire(participant: ApplicationParticipant) -> None:
    participant.is_active = False
    participant.save()


# --- Perfil financiero -----------------------------------------------------------------


def test_profile_not_found_until_created(
    advisor_client: APIClient, primary: ApplicationParticipant
) -> None:
    assert_error(advisor_client.get(profile_url(primary)), 404, "RESOURCE_NOT_FOUND")


def test_put_creates_the_profile(
    advisor_client: APIClient,
    advisor_user: User,
    application: CreditApplication,
    primary: ApplicationParticipant,
    django_capture_on_commit_callbacks: Any,
) -> None:
    received: list[dict[str, Any]] = []

    def on_updated(**kwargs: Any) -> None:
        received.append(kwargs)

    application_updated.connect(on_updated)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = put(advisor_client, primary, PROFILE)
    finally:
        application_updated.disconnect(on_updated)

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["participant_id"] == str(primary.id)
    assert body["employment_profile"]["code"] == "EMPLOYEE"
    assert body["contract_type"]["code"] == "INDEFINITE"
    assert body["funds_origin"]["code"] == "SALARY"
    assert body["employment_start_date"] == "2022-02-01"
    assert body["monthly_income_cop"] == 7_800_000
    assert body["income_sources_total_cop"] == 0
    assert body["data_confirmed_at"] is None
    assert version_of(application) == 2
    assert [(event["fields"], event["actor"]) for event in received] == [
        (["financial_profile"], advisor_user)
    ]

    detail = advisor_client.get(profile_url(primary))
    assert detail.status_code == 200
    assert detail["ETag"] == '"2"'
    participant = advisor_client.get(f"{PARTICIPANTS_URL}/{primary.id}").json()
    assert participant["financial_profile_id"] == body["id"]


def test_put_replaces_every_field(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
) -> None:
    put(advisor_client, primary, PROFILE)

    response = put(
        advisor_client,
        primary,
        {"employment_profile_code": "PENSIONER", "monthly_income_cop": 4_000_000},
        if_match='"2"',
    )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"3"'
    body = response.json()
    assert body["employment_profile"]["code"] == "PENSIONER"
    assert body["contract_type"] is None
    assert body["funds_origin"] is None
    assert body["employer_name"] == ""
    assert body["employment_start_date"] is None
    assert body["assets_cop"] == 0
    assert FinancialProfile.objects.filter(participant=primary).count() == 1


def test_put_with_the_same_data_keeps_the_version(
    advisor_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    put(advisor_client, primary, PROFILE)

    response = put(advisor_client, primary, PROFILE, if_match='"2"')

    assert response.status_code == 200
    assert response["ETag"] == '"2"'
    assert version_of(application) == 2


def test_put_requires_a_current_version(
    advisor_client: APIClient, primary: ApplicationParticipant
) -> None:
    assert_error(put(advisor_client, primary, PROFILE, if_match=None), 428, "PRECONDITION_REQUIRED")
    assert_error(put(advisor_client, primary, PROFILE, if_match='"5"'), 409, "STALE_VERSION")
    assert not FinancialProfile.objects.exists()


def test_put_requires_the_employment_profile(
    advisor_client: APIClient, primary: ApplicationParticipant
) -> None:
    payload = {key: value for key, value in PROFILE.items() if key != "employment_profile_code"}

    body = assert_error(put(advisor_client, primary, payload), 400, "VALIDATION_ERROR")

    assert body["details"][0]["field"] == "employment_profile_code"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"employment_profile_code": None}, "employment_profile_code"),
        ({"employment_profile_code": "ASTRONAUT"}, "employment_profile_code"),
        ({"contract_type_code": "FOREVER"}, "contract_type_code"),
        ({"monthly_income_cop": -1}, "monthly_income_cop"),
        (
            {"employment_start_date": (date.today() + timedelta(days=2)).isoformat()},
            "employment_start_date",
        ),
        ({"employment_type_code": "EMPLOYEE"}, "employment_type_code"),
        ({"data_confirmed_at": "2026-11-01T10:00:00Z"}, "data_confirmed_at"),
    ],
)
def test_put_validates_input(
    advisor_client: APIClient,
    primary: ApplicationParticipant,
    changes: dict[str, Any],
    field: str,
) -> None:
    payload = {**PROFILE, **changes}

    body = assert_error(put(advisor_client, primary, payload), 400, "VALIDATION_ERROR")

    assert field in {detail["field"] for detail in body["details"]}


def test_profile_of_a_retired_participant_is_read_only(
    admin_client: APIClient, primary: ApplicationParticipant, profile: FinancialProfile
) -> None:
    retire(primary)

    assert admin_client.get(profile_url(primary)).status_code == 200
    assert_error(put(admin_client, primary, PROFILE), 409, "PARTICIPANT_INACTIVE")


def test_profile_is_frozen_from_filing(
    advisor_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    application.status = ApplicationStatus.FILED
    application.save()

    assert_error(put(advisor_client, primary, PROFILE), 409, "APPLICATION_NOT_EDITABLE")


def test_profiles_are_hidden_from_brokers_and_other_advisors(
    broker_client: APIClient,
    broker_user: User,
    other_advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    profile: FinancialProfile,
) -> None:
    source = make_source(profile, 1_000_000)
    opportunity = application.opportunity
    opportunity.origin_user = broker_user
    opportunity.save()

    for url in (profile_url(primary), sources_url(profile)):
        assert_error(broker_client.get(url), 403, "PERMISSION_DENIED")
        assert_error(other_advisor_client.get(url), 404, "RESOURCE_NOT_FOUND")
    assert_error(patch_source(broker_client, source, {"notes": "x"}), 403, "PERMISSION_DENIED")
    assert_error(
        patch_source(other_advisor_client, source, {"notes": "x"}), 404, "RESOURCE_NOT_FOUND"
    )
    assert_error(other_advisor_client.delete(source_url(source)), 404, "RESOURCE_NOT_FOUND")


# --- Fuentes de ingreso ----------------------------------------------------------------


def test_add_income_source_bumps_version_and_updates_the_total(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    profile: FinancialProfile,
) -> None:
    response = advisor_client.post(sources_url(profile), SALARY, format="json")

    assert response.status_code == 201, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["financial_profile_id"] == str(profile.id)
    assert body["source_type"]["code"] == "SALARY"
    assert body["monthly_amount_cop"] == 7_000_000
    assert body["is_primary"] is True
    assert body["start_date"] is None

    advisor_client.post(
        sources_url(profile),
        {"source_type_code": "RENTAL", "monthly_amount_cop": 1_500_000},
        format="json",
    )
    # La suma no tiene que coincidir con el ingreso declarado: solo se informa.
    total = advisor_client.get(profile_url(primary)).json()
    assert total["income_sources_total_cop"] == 8_500_000
    assert total["monthly_income_cop"] == 7_800_000
    assert version_of(application) == 3


def test_new_primary_source_unmarks_the_previous_one(
    advisor_client: APIClient, profile: FinancialProfile
) -> None:
    previous = make_source(profile, 5_000_000, is_primary=True)

    response = advisor_client.post(
        sources_url(profile),
        {"source_type_code": "PENSION", "monthly_amount_cop": 3_000_000, "is_primary": True},
        format="json",
    )

    assert response.status_code == 201, response.content
    previous.refresh_from_db()
    assert previous.is_primary is False
    listing = advisor_client.get(sources_url(profile))
    assert listing.status_code == 200
    assert listing["ETag"] == '"2"'
    assert [row["is_primary"] for row in listing.json()["items"]] == [True, False]
    assert listing.json()["items"][0]["id"] == response.json()["id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"monthly_amount_cop": 1},
        {"source_type_code": "LOTTERY", "monthly_amount_cop": 1},
        {"source_type_code": "SALARY", "monthly_amount_cop": -5},
        {"source_type_code": "SALARY", "monthly_amount_cop": 1, "currency": "USD"},
    ],
)
def test_add_income_source_validates_input(
    advisor_client: APIClient, profile: FinancialProfile, payload: dict[str, Any]
) -> None:
    response = advisor_client.post(sources_url(profile), payload, format="json")

    assert_error(response, 400, "VALIDATION_ERROR")
    assert not profile.income_sources.exists()


def test_patch_income_source(
    advisor_client: APIClient, application: CreditApplication, profile: FinancialProfile
) -> None:
    primary_source = make_source(profile, 5_000_000, is_primary=True)
    other = make_source(profile, 1_000_000)

    assert_error(
        patch_source(advisor_client, other, {"is_primary": True}, if_match=None),
        428,
        "PRECONDITION_REQUIRED",
    )
    response = patch_source(
        advisor_client,
        other,
        {"is_primary": True, "monthly_amount_cop": 1_200_000, "start_date": "2024-03-01"},
    )

    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["is_primary"] is True
    assert body["monthly_amount_cop"] == 1_200_000
    assert body["start_date"] == "2024-03-01"
    primary_source.refresh_from_db()
    assert primary_source.is_primary is False

    same = patch_source(advisor_client, other, {"is_primary": True}, if_match='"2"')
    assert same.status_code == 200
    assert same["ETag"] == '"2"'
    stale = patch_source(advisor_client, other, {"notes": "Bono"}, if_match='"1"')
    assert_error(stale, 409, "STALE_VERSION")


def test_delete_income_source(
    advisor_client: APIClient, application: CreditApplication, profile: FinancialProfile
) -> None:
    source = make_source(profile, 5_000_000)

    response = advisor_client.delete(source_url(source))

    assert response.status_code == 204
    assert response["ETag"] == '"2"'
    assert not IncomeSource.objects.filter(pk=source.pk).exists()
    assert_error(advisor_client.delete(source_url(source)), 404, "RESOURCE_NOT_FOUND")


def test_income_sources_of_a_retired_participant_are_read_only(
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    profile: FinancialProfile,
) -> None:
    source = make_source(profile, 5_000_000)
    retire(primary)

    assert advisor_client.get(sources_url(profile)).status_code == 200
    assert_error(
        advisor_client.post(sources_url(profile), SALARY, format="json"),
        409,
        "PARTICIPANT_INACTIVE",
    )
    assert_error(patch_source(advisor_client, source, {"notes": "x"}), 409, "PARTICIPANT_INACTIVE")
    assert_error(advisor_client.delete(source_url(source)), 409, "PARTICIPANT_INACTIVE")
    assert version_of(application) == 1


def test_income_sources_are_frozen_from_filing(
    advisor_client: APIClient, application: CreditApplication, profile: FinancialProfile
) -> None:
    source = make_source(profile, 5_000_000)
    application.status = ApplicationStatus.FILED
    application.save()

    assert_error(
        advisor_client.post(sources_url(profile), SALARY, format="json"),
        409,
        "APPLICATION_NOT_EDITABLE",
    )
    assert_error(
        patch_source(advisor_client, source, {"notes": "x"}), 409, "APPLICATION_NOT_EDITABLE"
    )
    assert_error(advisor_client.delete(source_url(source)), 409, "APPLICATION_NOT_EDITABLE")
