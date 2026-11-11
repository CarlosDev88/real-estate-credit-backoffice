from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from pytest_django import DjangoAssertNumQueries
from rest_framework.test import APIClient

from apps.documents.models import DocumentRequirement, DocumentType
from apps.documents.services import ChecklistCase, ParticipantCase, preview_checklist
from tests.documents.conftest import PREVIEW_URL, catalog_item, seeded_product
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

BANCOLOMBIA_BASE = ["IDENTITY_DOCUMENT", "INCOME_RETENTION_CERTIFICATE", "INCOME_TAX_RETURN"]


def preview(api: APIClient, **payload: Any) -> Any:
    payload.setdefault("participants", [{"role": "PRIMARY"}])
    return api.post(PREVIEW_URL, payload, format="json")


def documents(response: Any, index: int = 0) -> list[str]:
    assert response.status_code == 200, response.content
    participant = response.json()["participants"][index]
    return [document["document_type"]["code"] for document in participant["documents"]]


def test_bancolombia_checklist_depends_on_each_participant_profile(
    advisor_client: APIClient,
) -> None:
    response = preview(
        advisor_client,
        bank_product_id=str(seeded_product("BANCOLOMBIA").id),
        purpose_code="PURCHASE_NEW",
        property_condition_code="NEW",
        participants=[
            {"role": "PRIMARY", "employment_profile_code": "EMPLOYEE"},
            {"role": "CO_APPLICANT", "employment_profile_code": "INDEPENDENT"},
            {"role": "SOLIDARY_DEBTOR", "employment_profile_code": "PENSIONER"},
            {"role": "CO_APPLICANT"},
        ],
    )

    assert documents(response, 0) == [
        *BANCOLOMBIA_BASE,
        "EMPLOYMENT_CERTIFICATE",
        "PAYROLL_SLIP",
    ]
    assert documents(response, 1) == [
        *BANCOLOMBIA_BASE,
        "BANK_STATEMENT",
        "INDEPENDENT_INCOME_SUPPORT",
    ]
    assert documents(response, 2) == [
        *BANCOLOMBIA_BASE,
        "PENSION_CERTIFICATE",
        "PENSION_PAYMENT_SLIP",
    ]
    # Sin perfil laboral solo aplican los requisitos que no dependen de él.
    assert documents(response, 3) == BANCOLOMBIA_BASE

    first = response.json()["participants"][0]
    assert (first["index"], first["role"]) == (0, "PRIMARY")
    assert first["employment_profile"] == {"code": "EMPLOYEE", "label": "Empleado"}
    by_code = {doc["document_type"]["code"]: doc for doc in first["documents"]}
    assert by_code["EMPLOYMENT_CERTIFICATE"]["validity_days"] == 30
    assert by_code["PAYROLL_SLIP"]["minimum_files"] == 3
    assert by_code["INCOME_TAX_RETURN"]["alternative_group_code"] == "INCOME_TAX_PROOF"
    assert by_code["INCOME_TAX_RETURN"]["is_waivable"] is True
    assert by_code["IDENTITY_DOCUMENT"]["is_general"] is False


def test_banks_without_requirements_return_an_empty_list(admin_client: APIClient) -> None:
    for bank_code in ("FNA", "BANCO_BOGOTA"):
        response = preview(
            admin_client,
            bank_product_id=str(seeded_product(bank_code).id),
            participants=[{"role": "PRIMARY", "employment_profile_code": "EMPLOYEE"}],
        )
        assert documents(response) == []


def test_general_requirements_apply_to_every_product(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    make_requirement(status="ACTIVE")

    fna = preview(admin_client, bank_product_id=str(seeded_product("FNA").id))
    no_product = preview(admin_client)

    assert documents(fna) == ["TEST_DOCUMENT"]
    assert fna.json()["participants"][0]["documents"][0]["is_general"] is True
    assert documents(no_product) == ["TEST_DOCUMENT"]


def test_requirement_with_a_purpose_or_condition_needs_that_value(
    admin_client: APIClient,
    make_type: Callable[..., DocumentType],
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(status="ACTIVE", purpose_item=catalog_item("loan_purpose", "PURCHASE_USED"))
    make_requirement(
        status="ACTIVE",
        document_type=make_type(code="PLAN_DOCUMENTS"),
        property_condition_item=catalog_item("property_condition", "OFF_PLAN"),
    )

    used = preview(admin_client, purpose_code="PURCHASE_USED")
    new = preview(admin_client, purpose_code="PURCHASE_NEW", property_condition_code="OFF_PLAN")
    unknown = preview(admin_client)

    assert documents(used) == ["TEST_DOCUMENT"]
    assert documents(new) == ["PLAN_DOCUMENTS"]
    assert documents(unknown) == []


def test_participant_role_limits_the_requirement(
    admin_client: APIClient, make_requirement: Callable[..., DocumentRequirement]
) -> None:
    make_requirement(status="ACTIVE", participant_role="SOLIDARY_DEBTOR")

    response = preview(
        admin_client, participants=[{"role": "PRIMARY"}, {"role": "SOLIDARY_DEBTOR"}]
    )

    assert documents(response, 0) == []
    assert documents(response, 1) == ["TEST_DOCUMENT"]


def test_only_active_current_versions_with_active_type_apply(
    admin_client: APIClient,
    make_type: Callable[..., DocumentType],
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    now = timezone.now()
    make_requirement()  # Borrador.
    make_requirement(
        document_type=make_type(code="FUTURE"),
        status="ACTIVE",
        valid_from=now + timedelta(days=5),
    )
    make_requirement(
        document_type=make_type(code="EXPIRED"),
        status="ACTIVE",
        valid_from=now - timedelta(days=10),
        valid_to=now - timedelta(days=1),
    )
    make_requirement(document_type=make_type(code="RETIRED"), status="INACTIVE")
    make_requirement(document_type=make_type(code="OFF_TYPE", is_active=False), status="ACTIVE")

    today = preview(admin_client)
    next_week = preview(admin_client, at=(now + timedelta(days=7)).isoformat())

    assert documents(today) == []
    assert documents(next_week) == ["FUTURE"]


def test_validity_falls_back_to_the_type_default(
    admin_client: APIClient,
    make_type: Callable[..., DocumentType],
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(
        document_type=make_type(code="WITH_DEFAULT", default_validity_days=90), status="ACTIVE"
    )

    response = preview(admin_client)

    assert response.json()["participants"][0]["documents"][0]["validity_days"] == 90


def test_preview_validates_the_case(admin_client: APIClient, broker_client: APIClient) -> None:
    assert_error(preview(admin_client, participants=[]), 400, "VALIDATION_ERROR")
    assert_error(
        preview(admin_client, participants=[{"role": "PRIMARY", "employment_profile_code": "X"}]),
        400,
        "VALIDATION_ERROR",
    )
    assert_error(
        preview(admin_client, participants=[{"role": "PRIMARY", "income": 1}]),
        400,
        "VALIDATION_ERROR",
    )
    assert_error(preview(broker_client), 403, "PERMISSION_DENIED")


def test_preview_runs_a_single_query(django_assert_num_queries: DjangoAssertNumQueries) -> None:
    product = seeded_product("BANCOLOMBIA")
    employee = catalog_item("employment_profile", "EMPLOYEE")
    independent = catalog_item("employment_profile", "INDEPENDENT")
    case = ChecklistCase(
        bank_product=product,
        participants=[
            ParticipantCase(role="PRIMARY", employment_profile=employee),
            ParticipantCase(role="CO_APPLICANT", employment_profile=independent),
            ParticipantCase(role="SOLIDARY_DEBTOR"),
        ],
    )

    with django_assert_num_queries(1):
        result = preview_checklist(case)
        validity = [
            req.effective_validity_days for item in result.participants for req in item.requirements
        ]

    assert [len(item.requirements) for item in result.participants] == [5, 5, 3]
    assert result.application_requirements == []
    assert 30 in validity


def test_application_documents_are_listed_once_outside_the_participants(
    admin_client: APIClient,
    make_type: Callable[..., DocumentType],
    make_requirement: Callable[..., DocumentRequirement],
) -> None:
    make_requirement(status="ACTIVE")
    budget = make_type(code="WORKS_BUDGET", holder_scope="APPLICATION")
    make_requirement(status="ACTIVE", document_type=budget)

    response = preview(admin_client, participants=[{"role": "PRIMARY"}, {"role": "CO_APPLICANT"}])

    assert documents(response, 0) == documents(response, 1) == ["TEST_DOCUMENT"]
    application_documents = response.json()["application_requirements"]
    assert [doc["document_type"]["code"] for doc in application_documents] == ["WORKS_BUDGET"]
    assert application_documents[0]["is_general"] is True


def test_preview_without_application_documents_returns_an_empty_list(
    admin_client: APIClient,
) -> None:
    response = preview(admin_client, bank_product_id=str(seeded_product("BANCOLOMBIA").id))

    assert response.status_code == 200, response.content
    assert response.json()["application_requirements"] == []
