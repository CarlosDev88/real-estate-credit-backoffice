"""Datos personales, perfiles financieros, ingresos y confirmación del comprador (Parte 5)."""

from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
    ParticipantRole,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, ClientAddress, Opportunity
from tests.applications.buyer_access.conftest import if_match, set_status, version_of
from tests.applications.conftest import catalog_item
from tests.helpers import assert_error, csrf_token

pytestmark = pytest.mark.django_db

PROFILE_BODY = {
    "employment_profile_code": "EMPLOYEE",
    "contract_type_code": "INDEFINITE",
    "employer_name": "Andina S.A.S.",
    "monthly_income_cop": 9_000_000,
    "monthly_expenses_cop": 3_000_000,
}


def profile_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/profile"


def participants_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/participants"


def financial_profile_url(participant: ApplicationParticipant) -> str:
    return f"/api/v1/buyer/participants/{participant.pk}/financial-profile"


def confirmation_url(participant: ApplicationParticipant) -> str:
    return f"{financial_profile_url(participant)}/confirmation"


def income_sources_url(profile: FinancialProfile) -> str:
    return f"/api/v1/buyer/financial-profiles/{profile.pk}/income-sources"


def income_source_url(source: IncomeSource) -> str:
    return f"/api/v1/buyer/income-sources/{source.pk}"


def make_profile(participant: ApplicationParticipant, **extra: Any) -> FinancialProfile:
    extra.setdefault("employment_profile_item", catalog_item("employment_profile", "EMPLOYEE"))
    extra.setdefault("monthly_income_cop", 5_000_000)
    return FinancialProfile.objects.create(participant=participant, **extra)


def make_source(profile: FinancialProfile, **extra: Any) -> IncomeSource:
    extra.setdefault("source_type_item", catalog_item("income_source_type", "SALARY"))
    extra.setdefault("monthly_amount_cop", 4_000_000)
    return IncomeSource.objects.create(financial_profile=profile, **extra)


def address(**extra: Any) -> dict[str, Any]:
    return {"address_type_code": "RESIDENCE", "city_code": "11001", "line1": "Calle 1", **extra}


@pytest.fixture
def co_applicant(
    application: CreditApplication, make_client: Callable[..., Client]
) -> ApplicationParticipant:
    return ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80999111", first_names="Pedro"),
        role=ParticipantRole.CO_APPLICANT,
    )


@pytest.fixture
def other_application(
    make_application: Callable[..., CreditApplication],
    make_opportunity: Callable[..., Opportunity],
    make_client: Callable[..., Client],
) -> CreditApplication:
    return make_application(make_opportunity(make_client(document_number="52000111")))


# --- Datos personales -------------------------------------------------------------------


def test_profile_shows_the_primary_with_a_masked_document(
    portal: APIClient, application: CreditApplication, buyer: Client
) -> None:
    ClientAddress.objects.create(
        client=buyer,
        address_type_item=catalog_item("address_type", "RESIDENCE"),
        city_item=catalog_item("municipality", "11001"),
        line1="Carrera 7 # 72-10",
        is_primary=True,
    )

    response = portal.get(profile_url(application))

    assert response.status_code == 200, response.content
    assert response["ETag"] == f'"{application.version}"'
    body = response.json()
    assert body["full_name"] == "Laura Gómez Vélez"
    assert body["document_type"]["code"] == "CC"
    assert body["document_number"] == "••••••5908"
    [item] = body["addresses"]
    assert set(item) == {
        "id",
        "address_type",
        "city",
        "line1",
        "line2",
        "postal_code",
        "is_primary",
    }
    assert item["line1"] == "Carrera 7 # 72-10"


def test_patch_contact_data(portal: APIClient, application: CreditApplication) -> None:
    before = version_of(application)

    response = portal.patch(
        profile_url(application),
        {"email": " Laura@Example.COM ", "phone": "+573001234567", "birth_date": "1990-04-02"},
        headers=if_match(application),
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["email"] == "laura@example.com"
    assert body["phone"] == "+573001234567"
    assert body["birth_date"] == "1990-04-02"
    assert version_of(application) == before + 1
    assert response["ETag"] == f'"{before + 1}"'

    # Los mismos datos no aumentan la versión.
    again = portal.patch(
        profile_url(application), {"email": "laura@example.com"}, headers=if_match(application)
    )
    assert again.status_code == 200
    assert version_of(application) == before + 1


@pytest.mark.parametrize(
    "payload",
    [
        {"first_names": "Otra"},
        {"document_number": "123"},
        {"birth_date": "2999-01-01"},
        {"phone": "no es un teléfono"},
        {"addresses": [address()] * 11},
    ],
)
def test_patch_rejects_fields_and_values_the_buyer_cannot_set(
    portal: APIClient, application: CreditApplication, payload: dict[str, Any]
) -> None:
    response = portal.patch(profile_url(application), payload, headers=if_match(application))

    assert_error(response, 400, "VALIDATION_ERROR")


def test_patch_requires_a_current_if_match(
    portal: APIClient, application: CreditApplication
) -> None:
    url = profile_url(application)
    assert_error(portal.patch(url, {"phone": ""}), 428, "PRECONDITION_REQUIRED")
    assert_error(
        portal.patch(url, {"phone": ""}, headers={"If-Match": '"99"'}), 409, "STALE_VERSION"
    )


def test_addresses_are_replaced_as_a_list(
    portal: APIClient, application: CreditApplication, buyer: Client
) -> None:
    created = portal.patch(
        profile_url(application),
        {"addresses": [address(line1="Casa"), address(line1="Oficina", address_type_code="WORK")]},
        headers=if_match(application),
    )
    assert created.status_code == 200, created.content
    first, second = created.json()["addresses"]
    by_line = {first["line1"]: first, second["line1"]: second}
    assert by_line["Casa"]["is_primary"] is True
    assert by_line["Oficina"]["is_primary"] is False

    version = version_of(application)
    updated = portal.patch(
        profile_url(application),
        {
            "addresses": [
                address(id=by_line["Oficina"]["id"], line1="Oficina 2", is_primary=True),
                address(line1="Finca", city_code="05001"),
            ]
        },
        headers=if_match(application),
    )

    assert updated.status_code == 200, updated.content
    lines = {item["line1"]: item for item in updated.json()["addresses"]}
    assert set(lines) == {"Oficina 2", "Finca"}
    assert lines["Oficina 2"]["id"] == by_line["Oficina"]["id"]
    assert lines["Oficina 2"]["is_primary"] is True
    assert lines["Finca"]["is_primary"] is False
    assert version_of(application) == version + 1

    # La misma lista no cambia nada.
    same = [
        address(id=lines["Oficina 2"]["id"], line1="Oficina 2", is_primary=True),
        address(id=lines["Finca"]["id"], line1="Finca", city_code="05001"),
    ]
    portal.patch(profile_url(application), {"addresses": same}, headers=if_match(application))
    assert version_of(application) == version + 1

    emptied = portal.patch(
        profile_url(application), {"addresses": []}, headers=if_match(application)
    )
    assert emptied.json()["addresses"] == []
    assert not buyer.addresses.exists()


def test_address_list_validation(
    portal: APIClient,
    application: CreditApplication,
    buyer: Client,
    make_client: Callable[..., Client],
) -> None:
    mine = ClientAddress.objects.create(
        client=buyer,
        address_type_item=catalog_item("address_type", "RESIDENCE"),
        city_item=catalog_item("municipality", "11001"),
        line1="Mía",
    )
    foreign = ClientAddress.objects.create(
        client=make_client(document_number="70111222"),
        address_type_item=catalog_item("address_type", "RESIDENCE"),
        city_item=catalog_item("municipality", "11001"),
        line1="Ajena",
    )
    cases = [
        [address(id=str(foreign.pk))],
        [address(id=str(mine.pk)), address(id=str(mine.pk))],
        [address(is_primary=True), address(is_primary=True)],
    ]
    for addresses in cases:
        response = portal.patch(
            profile_url(application), {"addresses": addresses}, headers=if_match(application)
        )
        assert_error(response, 400, "VALIDATION_ERROR")

    foreign.refresh_from_db()
    assert foreign.line1 == "Ajena"
    assert list(buyer.addresses.values_list("line1", flat=True)) == ["Mía"]


# --- Estado de la solicitud y bloqueos --------------------------------------------------


def test_after_filed_the_data_is_not_editable(
    portal: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    make_profile(primary)
    set_status(application, ApplicationStatus.FILED)

    assert_error(
        portal.patch(profile_url(application), {"phone": ""}, headers=if_match(application)),
        409,
        "APPLICATION_NOT_EDITABLE",
    )
    assert_error(
        portal.put(financial_profile_url(primary), PROFILE_BODY, headers=if_match(application)),
        409,
        "APPLICATION_NOT_EDITABLE",
    )
    assert_error(
        portal.post(confirmation_url(primary), headers=if_match(application)),
        409,
        "APPLICATION_NOT_EDITABLE",
    )
    # Leer sigue permitido.
    assert portal.get(financial_profile_url(primary)).status_code == 200


def test_closed_application_is_read_only_before_asking_for_consents(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.WITHDRAWN)

    response = buyer_client.patch(
        profile_url(application), {"phone": ""}, headers=if_match(application)
    )

    assert_error(response, 409, "APPLICATION_CLOSED")
    assert buyer_client.get(profile_url(application)).status_code == 200


def test_pending_consents_block_editing(
    buyer_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    assert_error(
        buyer_client.patch(profile_url(application), {"phone": ""}, headers=if_match(application)),
        403,
        "CONSENT_REQUIRED",
    )
    assert_error(
        buyer_client.put(
            financial_profile_url(primary), PROFILE_BODY, headers=if_match(application)
        ),
        403,
        "CONSENT_REQUIRED",
    )
    assert buyer_client.get(participants_url(application)).status_code == 200


def test_editing_requires_csrf(
    buyer_csrf_client: APIClient,
    accept_consents: Callable[[], None],
    application: CreditApplication,
) -> None:
    accept_consents()
    url = profile_url(application)
    assert_error(
        buyer_csrf_client.patch(url, {"phone": ""}, headers=if_match(application)),
        403,
        "CSRF_FAILED",
    )

    response = buyer_csrf_client.patch(
        url,
        {"phone": ""},
        HTTP_X_CSRFTOKEN=csrf_token(buyer_csrf_client),
        headers=if_match(application),
    )

    assert response.status_code == 200


def test_resources_of_another_application_are_not_found(
    portal: APIClient, other_application: CreditApplication
) -> None:
    other_primary = other_application.participants.get()
    other_profile = make_profile(other_primary)
    other_source = make_source(other_profile)

    for url in (
        profile_url(other_application),
        participants_url(other_application),
        financial_profile_url(other_primary),
        income_sources_url(other_profile),
    ):
        assert_error(portal.get(url), 404, "RESOURCE_NOT_FOUND")
    assert_error(
        portal.patch(
            income_source_url(other_source), {"payer_name": "x"}, headers={"If-Match": '"1"'}
        ),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error(portal.delete(income_source_url(other_source)), 404, "RESOURCE_NOT_FOUND")
    assert IncomeSource.objects.filter(pk=other_source.pk).exists()


def test_internal_session_does_not_open_buyer_editing(
    advisor_client: APIClient, primary: ApplicationParticipant
) -> None:
    assert_error(advisor_client.get(financial_profile_url(primary)), 401, "NOT_AUTHENTICATED")


# --- Participantes y perfil financiero --------------------------------------------------


def test_participants_are_the_active_ones(
    portal: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    co_applicant: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> None:
    debtor = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80999222", first_names="Rosa"),
        role=ParticipantRole.SOLIDARY_DEBTOR,
    )
    ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80999333"),
        role=ParticipantRole.CO_APPLICANT,
        is_active=False,
    )
    profile = make_profile(co_applicant)

    response = portal.get(participants_url(application))

    assert response.status_code == 200, response.content
    assert "ETag" in response
    items = {item["id"]: item for item in response.json()["items"]}
    assert set(items) == {str(primary.pk), str(co_applicant.pk), str(debtor.pk)}
    assert items[str(primary.pk)]["financial_profile_id"] is None
    assert items[str(co_applicant.pk)] == {
        "id": str(co_applicant.pk),
        "role": "CO_APPLICANT",
        "role_label": "Co-solicitante",
        "full_name": "Pedro Gómez Vélez",
        "contributes_income": True,
        "financial_profile_id": str(profile.pk),
        "data_confirmed_at": None,
    }


def test_put_financial_profile_of_a_co_applicant(
    portal: APIClient, application: CreditApplication, co_applicant: ApplicationParticipant
) -> None:
    url = financial_profile_url(co_applicant)
    assert_error(portal.get(url), 404, "RESOURCE_NOT_FOUND")
    before = version_of(application)

    created = portal.put(url, PROFILE_BODY, headers=if_match(application))

    assert created.status_code == 201, created.content
    body = created.json()
    assert body["participant_id"] == str(co_applicant.pk)
    assert body["employment_profile"]["code"] == "EMPLOYEE"
    assert body["monthly_income_cop"] == 9_000_000
    assert body["data_confirmed_at"] is None
    assert version_of(application) == before + 1
    assert created["ETag"] == f'"{before + 1}"'

    updated = portal.put(url, {**PROFILE_BODY, "assets_cop": 1}, headers=if_match(application))
    assert updated.status_code == 200
    assert updated.json()["assets_cop"] == 1

    assert_error(
        portal.put(url, {**PROFILE_BODY, "data_confirmed_at": "2026-01-01T00:00:00Z"}),
        428,
        "PRECONDITION_REQUIRED",
    )
    response = portal.put(
        url,
        {**PROFILE_BODY, "data_confirmed_at": "2026-01-01T00:00:00Z"},
        headers=if_match(application),
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_inactive_participant_is_not_found(
    portal: APIClient, application: CreditApplication, co_applicant: ApplicationParticipant
) -> None:
    ApplicationParticipant.objects.filter(pk=co_applicant.pk).update(is_active=False)

    response = portal.put(
        financial_profile_url(co_applicant), PROFILE_BODY, headers=if_match(application)
    )

    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_confirmation(
    portal: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    url = confirmation_url(primary)
    assert_error(portal.post(url, headers=if_match(application)), 404, "RESOURCE_NOT_FOUND")
    profile = make_profile(primary)
    assert_error(portal.post(url), 428, "PRECONDITION_REQUIRED")
    before = version_of(application)

    response = portal.post(url, headers=if_match(application))

    assert response.status_code == 200, response.content
    profile.refresh_from_db()
    assert profile.data_confirmed_at is not None
    assert response.json()["data_confirmed_at"] is not None
    assert version_of(application) == before + 1

    confirmed_at = profile.data_confirmed_at
    again = portal.post(url, headers=if_match(application))
    assert again.status_code == 200
    profile.refresh_from_db()
    assert profile.data_confirmed_at == confirmed_at
    assert version_of(application) == before + 1

    listed = portal.get(participants_url(application)).json()["items"]
    assert listed[0]["data_confirmed_at"] is not None


def confirm(profile: FinancialProfile) -> None:
    FinancialProfile.objects.filter(pk=profile.pk).update(data_confirmed_at=timezone.now())


def is_confirmed(profile: FinancialProfile) -> bool:
    profile.refresh_from_db()
    return profile.data_confirmed_at is not None


def test_real_changes_clear_the_confirmation(
    portal: APIClient,
    advisor_client: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
) -> None:
    portal.put(financial_profile_url(primary), PROFILE_BODY, headers=if_match(application))
    profile = FinancialProfile.objects.get(participant=primary)

    # Los mismos datos no son un cambio.
    confirm(profile)
    portal.put(financial_profile_url(primary), PROFILE_BODY, headers=if_match(application))
    assert is_confirmed(profile)

    # Un cambio del comprador.
    portal.put(
        financial_profile_url(primary),
        {**PROFILE_BODY, "assets_cop": 5},
        headers=if_match(application),
    )
    assert not is_confirmed(profile)

    # Un cambio del asesor en el endpoint interno.
    confirm(profile)
    internal = advisor_client.put(
        f"/api/v1/application-participants/{primary.pk}/financial-profile",
        {**PROFILE_BODY, "assets_cop": 6},
        headers=if_match(application),
    )
    assert internal.status_code == 200, internal.content
    assert not is_confirmed(profile)

    # Agregar, editar y borrar ingresos.
    confirm(profile)
    created = portal.post(
        income_sources_url(profile), {"source_type_code": "SALARY", "monthly_amount_cop": 1}
    )
    assert created.status_code == 201, created.content
    assert not is_confirmed(profile)

    source = IncomeSource.objects.get(pk=created.json()["id"])
    confirm(profile)
    portal.patch(
        income_source_url(source), {"monthly_amount_cop": 1}, headers=if_match(application)
    )
    assert is_confirmed(profile)
    portal.patch(
        income_source_url(source), {"monthly_amount_cop": 2}, headers=if_match(application)
    )
    assert not is_confirmed(profile)

    confirm(profile)
    assert portal.delete(income_source_url(source)).status_code == 204
    assert not is_confirmed(profile)


# --- Fuentes de ingreso -----------------------------------------------------------------


def test_income_sources_crud(
    portal: APIClient, application: CreditApplication, co_applicant: ApplicationParticipant
) -> None:
    profile = make_profile(co_applicant)
    url = income_sources_url(profile)

    assert_error(
        portal.post(url, {"source_type_code": "SALARY", "monthly_amount_cop": 1, "notes": "x"}),
        400,
        "VALIDATION_ERROR",
    )
    created = portal.post(
        url, {"source_type_code": "SALARY", "monthly_amount_cop": 3_000_000, "is_primary": True}
    )
    assert created.status_code == 201, created.content
    assert "ETag" in created
    body = created.json()
    assert set(body) == {
        "id",
        "financial_profile_id",
        "source_type",
        "payer_name",
        "monthly_amount_cop",
        "start_date",
        "is_primary",
        "updated_at",
    }

    listed = portal.get(url)
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]
    assert portal.get(financial_profile_url(co_applicant)).json()["income_sources_total_cop"] == (
        3_000_000
    )

    source = IncomeSource.objects.get(pk=body["id"])
    assert_error(
        portal.patch(income_source_url(source), {"payer_name": "Andina"}),
        428,
        "PRECONDITION_REQUIRED",
    )
    patched = portal.patch(
        income_source_url(source), {"payer_name": "Andina"}, headers=if_match(application)
    )
    assert patched.status_code == 200
    assert patched.json()["payer_name"] == "Andina"

    deleted = portal.delete(income_source_url(source))
    assert deleted.status_code == 204
    assert "ETag" in deleted
    assert not IncomeSource.objects.filter(pk=source.pk).exists()


def test_buyer_income_source_hides_the_advisor_notes(
    portal: APIClient, primary: ApplicationParticipant
) -> None:
    profile = make_profile(primary)
    make_source(profile, notes="Nota interna del asesor")

    [item] = portal.get(income_sources_url(profile)).json()["items"]

    assert "notes" not in item
