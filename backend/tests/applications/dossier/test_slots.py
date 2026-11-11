"""Materialización y recálculo de slots (``documents.slots.sync_slots``) y sus llamadas
desde los servicios de ``applications`` (decisión 6, acordadas 3, 4 y 5)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications import services
from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
)
from apps.crm.models import Client
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentRequirement,
    DocumentType,
    ParticipantRole,
    RequirementStatus,
    SlotStatus,
)
from apps.documents.slots import SlotSync, merge_requirements, sync_slots
from apps.identity.models import User
from tests.applications.conftest import application_url, catalog_item, seeded_product
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory
from tests.applications.test_applications_api import create
from tests.applications.test_property_financing_api import (
    PROPERTY,
    USED_PROPERTY,
    bank_credit,
)
from tests.applications.test_property_financing_api import put as put_resource

pytestmark = pytest.mark.django_db

# Lo que el checklist sembrado de Bancolombia pide a cualquier participante.
BASE_SET = [
    ("IDENTITY_DOCUMENT", 1),
    ("INCOME_RETENTION_CERTIFICATE", 1),
    ("INCOME_TAX_RETURN", 1),
]
EMPLOYEE_SET = [
    ("EMPLOYMENT_CERTIFICATE", 1),
    ("PAYROLL_SLIP", 1),
    ("PAYROLL_SLIP", 2),
    ("PAYROLL_SLIP", 3),
]
INDEPENDENT_SET = [
    ("BANK_STATEMENT", 1),
    ("BANK_STATEMENT", 2),
    ("BANK_STATEMENT", 3),
    ("INDEPENDENT_INCOME_SUPPORT", 1),
]


def sync(application: CreditApplication) -> SlotSync:
    with transaction.atomic():
        locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
        return sync_slots(locked)


def active(application: CreditApplication) -> Any:
    return ApplicationDocumentSlot.objects.filter(application=application, retired_at__isnull=True)


def held(
    application: CreditApplication, participant: ApplicationParticipant | None
) -> list[tuple[str, int]]:
    """(tipo, índice) de los slots vigentes de un titular, ordenados."""
    rows = active(application).filter(participant=participant)
    return sorted(rows.values_list("document_type__code", "slot_index"))


def set_profile(participant: ApplicationParticipant, code: str) -> None:
    FinancialProfile.objects.update_or_create(
        participant=participant,
        defaults={"employment_profile_item": catalog_item("employment_profile", code)},
    )


def requirement(type_code: str, **extra: Any) -> DocumentRequirement:
    """Requisito general (sin producto) publicado."""
    extra.setdefault("version", 1)
    extra.setdefault("status", RequirementStatus.ACTIVE)
    extra.setdefault("valid_from", timezone.now() - timedelta(days=1))
    extra.setdefault("is_required", True)
    return DocumentRequirement.objects.create(
        document_type=DocumentType.objects.get(code=type_code), **extra
    )


def seeded_requirement(type_code: str) -> DocumentRequirement:
    return DocumentRequirement.objects.get(
        bank_product=seeded_product(), document_type__code=type_code, version=1
    )


def publish_version(previous: DocumentRequirement, **changes: Any) -> DocumentRequirement:
    """Nueva versión publicada del mismo alcance; la anterior queda inactiva."""
    previous.status = RequirementStatus.INACTIVE
    previous.save(update_fields=["status"])
    values = {
        "bank_product": previous.bank_product,
        "document_type": previous.document_type,
        "purpose_item": previous.purpose_item,
        "employment_profile_item": previous.employment_profile_item,
        "participant_role": previous.participant_role,
        "property_condition_item": previous.property_condition_item,
        "is_required": previous.is_required,
        "is_waivable": previous.is_waivable,
        "minimum_files": previous.minimum_files,
        "alternative_group_code": previous.alternative_group_code,
        "validity_days": previous.validity_days,
        "sort_order": previous.sort_order,
        "valid_from": previous.valid_from,
        **changes,
    }
    return DocumentRequirement.objects.create(
        **values, version=previous.version + 1, status=RequirementStatus.ACTIVE
    )


@pytest.fixture
def with_product(application: CreditApplication) -> CreditApplication:
    application.bank_product = seeded_product()
    application.save(update_fields=["bank_product"])
    return application


@pytest.fixture
def co_applicant(
    application: CreditApplication, make_client: Callable[..., Client]
) -> ApplicationParticipant:
    client = make_client(document_number="80123456", first_names="Andrés")
    return ApplicationParticipant.objects.create(
        application=application, client=client, role=ParticipantRole.CO_APPLICANT
    )


# --- Materialización --------------------------------------------------------------------


def test_without_product_only_general_requirements_apply(
    application: CreditApplication,
) -> None:
    result = sync(application)

    assert not result.changed
    assert not active(application).exists()


def test_the_product_checklist_is_copied_as_a_snapshot(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    result = sync(with_product)

    assert held(with_product, primary) == BASE_SET
    assert len(result.created) == 3
    assert result.retired == result.revived == result.updated == []
    identity = active(with_product).get(document_type__code="IDENTITY_DOCUMENT")
    source = seeded_requirement("IDENTITY_DOCUMENT")
    assert identity.requirement_id == source.pk
    assert identity.requirement_version == 1
    assert identity.status == SlotStatus.PENDING
    assert (identity.is_required, identity.is_waivable, identity.minimum_files) == (
        True,
        False,
        1,
    )
    assert identity.sort_order == source.sort_order
    retention = active(with_product).get(document_type__code="INCOME_RETENTION_CERTIFICATE")
    assert retention.alternative_group_code == "INCOME_TAX_PROOF"
    assert retention.is_waivable is True


def test_a_requirement_with_several_files_creates_one_slot_per_file(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")

    sync(with_product)

    assert held(with_product, primary) == sorted(BASE_SET + EMPLOYEE_SET)
    payroll = active(with_product).filter(document_type__code="PAYROLL_SLIP")
    assert set(payroll.values_list("minimum_files", flat=True)) == {3}
    certificate = active(with_product).get(document_type__code="EMPLOYMENT_CERTIFICATE")
    assert certificate.validity_days == 30


def test_validity_falls_back_to_the_document_type_default(
    application: CreditApplication,
) -> None:
    DocumentType.objects.filter(code="BANK_STATEMENT").update(default_validity_days=45)
    requirement("BANK_STATEMENT")

    sync(application)

    assert active(application).get().validity_days == 45


def test_sync_is_idempotent(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)

    result = sync(with_product)

    assert not result.changed


def test_each_active_participant_gets_its_own_set(
    with_product: CreditApplication,
    primary: ApplicationParticipant,
    co_applicant: ApplicationParticipant,
) -> None:
    set_profile(co_applicant, "PENSIONER")

    sync(with_product)

    assert held(with_product, primary) == BASE_SET
    assert held(with_product, co_applicant) == sorted(
        BASE_SET
        + [
            ("PENSION_CERTIFICATE", 1),
            ("PENSION_PAYMENT_SLIP", 1),
            ("PENSION_PAYMENT_SLIP", 2),
            ("PENSION_PAYMENT_SLIP", 3),
        ]
    )


def test_role_requirements_only_reach_that_role(
    application: CreditApplication,
    primary: ApplicationParticipant,
    co_applicant: ApplicationParticipant,
) -> None:
    requirement("EMPLOYMENT_CERTIFICATE", participant_role=ParticipantRole.CO_APPLICANT)

    sync(application)

    assert held(application, primary) == []
    assert held(application, co_applicant) == [("EMPLOYMENT_CERTIFICATE", 1)]


def test_application_documents_are_requested_once(
    application: CreditApplication,
    primary: ApplicationParticipant,
    co_applicant: ApplicationParticipant,
) -> None:
    requirement("PROPERTY_OWNERSHIP_DOCUMENT")

    sync(application)

    assert held(application, None) == [("PROPERTY_OWNERSHIP_DOCUMENT", 1)]
    assert held(application, primary) == held(application, co_applicant) == []


def test_property_condition_requirements_follow_the_property(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    requirement(
        "PROPERTY_ANALYSIS_DOCUMENTS",
        property_condition_item=catalog_item("property_condition", "USED"),
    )
    sync(application)
    assert held(application, None) == []

    response = put_resource(advisor_client, application, "property", USED_PROPERTY)

    assert response.status_code == 201, response.content
    assert held(application, None) == [("PROPERTY_ANALYSIS_DOCUMENTS", 1)]


# --- Tipo repetido (decisión 17) -----------------------------------------------------


def test_a_repeated_type_creates_one_set_with_the_strictest_combination(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")
    requirement(
        "PAYROLL_SLIP",
        employment_profile_item=catalog_item("employment_profile", "EMPLOYEE"),
        is_required=False,
        is_waivable=True,
        minimum_files=4,
        validity_days=45,
        sort_order=5,
    )

    sync(with_product)

    payroll = active(with_product).filter(document_type__code="PAYROLL_SLIP")
    assert sorted(payroll.values_list("slot_index", flat=True)) == [1, 2, 3, 4]
    slot = payroll.first()
    assert slot is not None
    # El del producto es obligatorio: es el más estricto y da id, versión y orden.
    assert slot.requirement_id == seeded_requirement("PAYROLL_SLIP").pk
    assert slot.sort_order == seeded_requirement("PAYROLL_SLIP").sort_order
    assert (slot.is_required, slot.is_waivable, slot.minimum_files, slot.validity_days) == (
        True,
        False,
        4,
        45,
    )


def test_a_repeated_type_stays_in_a_group_only_if_every_requirement_is(
    with_product: CreditApplication,
) -> None:
    requirement("INCOME_TAX_RETURN", is_waivable=True)

    sync(with_product)

    tax_return = active(with_product).get(document_type__code="INCOME_TAX_RETURN")
    assert tax_return.alternative_group_code is None
    assert tax_return.is_waivable is True


def test_merge_prefers_a_validity_and_breaks_ties_deterministically() -> None:
    document_type = DocumentType.objects.get(code="BANK_STATEMENT")
    common: dict[str, Any] = {
        "document_type": document_type,
        "version": 1,
        "is_required": True,
        "minimum_files": 1,
        "valid_from": timezone.now(),
    }
    with_validity = DocumentRequirement(validity_days=60, **common)
    without = DocumentRequirement(validity_days=None, **common)

    assert merge_requirements([without, with_validity]).requirement_id == with_validity.pk
    assert merge_requirements([with_validity, without]).validity_days == 60
    twin = DocumentRequirement(validity_days=60, **common)
    first = merge_requirements([with_validity, twin]).requirement_id
    assert merge_requirements([twin, with_validity]).requirement_id == first


# --- Recálculo (acordada 5) -------------------------------------------------------------


def test_a_profile_change_retires_and_a_return_revives_the_same_slots(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)
    employee_ids = set(
        active(with_product)
        .filter(document_type__code__in=["EMPLOYMENT_CERTIFICATE", "PAYROLL_SLIP"])
        .values_list("pk", flat=True)
    )

    set_profile(primary, "INDEPENDENT")
    result = sync(with_product)

    assert set(result.retired) == employee_ids
    assert len(result.created) == 4
    assert held(with_product, primary) == sorted(BASE_SET + INDEPENDENT_SET)
    retired = ApplicationDocumentSlot.objects.filter(pk__in=employee_ids)
    assert all(slot.retired_at is not None for slot in retired)

    set_profile(primary, "EMPLOYEE")
    result = sync(with_product)

    assert set(result.revived) == employee_ids
    assert result.created == []
    assert held(with_product, primary) == sorted(BASE_SET + EMPLOYEE_SET)


def test_an_inactive_participant_loses_its_slots(
    with_product: CreditApplication, co_applicant: ApplicationParticipant
) -> None:
    sync(with_product)
    co_applicant.is_active = False
    co_applicant.save(update_fields=["is_active"])

    result = sync(with_product)

    assert len(result.retired) == 3
    assert held(with_product, co_applicant) == []


def test_lowering_minimum_files_retires_the_highest_index(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)
    third = active(with_product).get(document_type__code="PAYROLL_SLIP", slot_index=3)
    v2 = publish_version(seeded_requirement("PAYROLL_SLIP"), minimum_files=2)

    result = sync(with_product)

    assert result.retired == [third.pk]
    assert len(result.updated) == 2
    payroll = active(with_product).filter(document_type__code="PAYROLL_SLIP")
    assert sorted(payroll.values_list("slot_index", flat=True)) == [1, 2]
    for slot in payroll:
        assert (slot.requirement_id, slot.requirement_version, slot.minimum_files) == (
            v2.pk,
            2,
            2,
        )


def test_a_slot_with_history_keeps_its_snapshot(
    with_product: CreditApplication,
    primary: ApplicationParticipant,
    make_document_file: DocumentFileFactory,
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)
    first = active(with_product).get(document_type__code="PAYROLL_SLIP", slot_index=1)
    make_document_file(slot=first)
    first.status = SlotStatus.UPLOADED
    first.save(update_fields=["status"])
    v2 = publish_version(seeded_requirement("PAYROLL_SLIP"), minimum_files=4, validity_days=60)

    result = sync(with_product)

    first.refresh_from_db()
    assert (first.requirement_version, first.minimum_files, first.validity_days) == (1, 3, None)
    assert first.pk not in result.updated
    payroll = active(with_product).filter(document_type__code="PAYROLL_SLIP")
    assert sorted(payroll.values_list("slot_index", flat=True)) == [1, 2, 3, 4]
    fourth = payroll.get(slot_index=4)
    assert (fourth.requirement_id, fourth.minimum_files, fourth.validity_days) == (v2.pk, 4, 60)
    assert payroll.get(slot_index=2).requirement_version == 2


def test_a_waived_slot_keeps_its_snapshot(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    sync(with_product)
    retention = active(with_product).get(document_type__code="INCOME_RETENTION_CERTIFICATE")
    retention.status = SlotStatus.WAIVED
    retention.waiver_reason_item = catalog_item("document_waiver_reason", "NOT_APPLICABLE")
    retention.save(update_fields=["status", "waiver_reason_item"])
    publish_version(seeded_requirement("INCOME_RETENTION_CERTIFICATE"), is_waivable=False)

    result = sync(with_product)

    retention.refresh_from_db()
    assert retention.is_waivable is True
    assert retention.requirement_version == 1
    assert result.updated == []


def test_a_revived_slot_with_history_keeps_its_status_and_snapshot(
    with_product: CreditApplication,
    primary: ApplicationParticipant,
    make_document_file: DocumentFileFactory,
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)
    certificate = active(with_product).get(document_type__code="EMPLOYMENT_CERTIFICATE")
    make_document_file(slot=certificate)
    certificate.status = SlotStatus.APPROVED
    certificate.save(update_fields=["status"])
    set_profile(primary, "INDEPENDENT")
    sync(with_product)
    publish_version(seeded_requirement("EMPLOYMENT_CERTIFICATE"), validity_days=15)
    set_profile(primary, "EMPLOYEE")

    result = sync(with_product)

    certificate.refresh_from_db()
    assert certificate.pk in result.revived
    assert certificate.retired_at is None
    assert certificate.status == SlotStatus.APPROVED
    assert (certificate.requirement_version, certificate.validity_days) == (1, 30)


def test_a_revived_slot_without_history_takes_the_current_requirement(
    with_product: CreditApplication, primary: ApplicationParticipant
) -> None:
    set_profile(primary, "EMPLOYEE")
    sync(with_product)
    set_profile(primary, "INDEPENDENT")
    sync(with_product)
    v2 = publish_version(seeded_requirement("EMPLOYMENT_CERTIFICATE"), validity_days=15)
    set_profile(primary, "EMPLOYEE")

    sync(with_product)

    certificate = active(with_product).get(document_type__code="EMPLOYMENT_CERTIFICATE")
    assert (certificate.requirement_id, certificate.validity_days) == (v2.pk, 15)


def test_among_several_retired_slots_the_one_with_history_revives(
    application: CreditApplication,
    make_slot: SlotFactory,
    make_document_file: DocumentFileFactory,
) -> None:
    now = timezone.now()
    with_history = make_slot(retired_at=now - timedelta(days=2))
    make_document_file(slot=with_history)
    make_slot(retired_at=now - timedelta(days=1))
    requirement("IDENTITY_DOCUMENT")

    result = sync(application)

    assert result.revived == [with_history.pk]
    assert active(application).get().pk == with_history.pk


def test_a_deactivated_requirement_retires_its_slots_on_the_next_sync(
    with_product: CreditApplication,
) -> None:
    sync(with_product)
    source = seeded_requirement("IDENTITY_DOCUMENT")
    source.status = RequirementStatus.INACTIVE
    source.save(update_fields=["status"])

    result = sync(with_product)

    assert len(result.retired) == 1
    assert not active(with_product).filter(document_type__code="IDENTITY_DOCUMENT").exists()


def test_sync_does_not_touch_the_application_version(
    with_product: CreditApplication,
) -> None:
    sync(with_product)

    with_product.refresh_from_db(fields=["version"])
    assert with_product.version == 1


# --- Llamadas desde los servicios de applications (decisión 6) ---------------------


@pytest.fixture
def sync_calls(monkeypatch: pytest.MonkeyPatch) -> list[CreditApplication]:
    """Registra cada llamada a ``sync_slots`` desde los servicios, sin dejar de hacerla."""
    calls: list[CreditApplication] = []

    def spy(locked: CreditApplication) -> SlotSync:
        calls.append(locked)
        return sync_slots(locked)

    monkeypatch.setattr(services, "sync_slots", spy)
    return calls


def test_creating_an_application_materializes_its_slots(
    advisor_client: APIClient, opportunity: Any
) -> None:
    requirement("IDENTITY_DOCUMENT")

    response = create(advisor_client, opportunity)

    assert response.status_code == 201, response.content
    application = CreditApplication.objects.get(pk=response.json()["id"])
    primary = application.participants.get()
    assert held(application, primary) == [("IDENTITY_DOCUMENT", 1)]


def test_choosing_a_product_materializes_its_checklist(
    advisor_user: User, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    services.update_application(
        advisor_user, application, expected_version=1, changes={"bank_product": seeded_product()}
    )

    assert held(application, primary) == BASE_SET


def test_financing_with_and_without_a_product_follows_the_checklist(
    advisor_client: APIClient, application: CreditApplication, primary: ApplicationParticipant
) -> None:
    response = put_resource(advisor_client, application, "financing", bank_credit())
    assert response.status_code == 201, response.content
    assert held(application, primary) == BASE_SET

    response = put_resource(
        advisor_client,
        application,
        "financing",
        {"financing_mode_code": "OWN_FUNDS", "own_resources_cop": 420_000_000},
        '"2"',
    )

    assert response.status_code == 200, response.content
    assert held(application, primary) == []


def test_financing_changes_without_a_new_product_do_not_resync(
    advisor_client: APIClient,
    application: CreditApplication,
    sync_calls: list[CreditApplication],
) -> None:
    put_resource(advisor_client, application, "financing", bank_credit())
    response = put_resource(
        advisor_client, application, "financing", bank_credit(term_months=180), '"2"'
    )

    assert response.status_code == 200, response.content
    assert len(sync_calls) == 1


def test_the_property_condition_resyncs_only_when_it_changes(
    advisor_client: APIClient,
    application: CreditApplication,
    sync_calls: list[CreditApplication],
) -> None:
    requirement(
        "PROPERTY_ANALYSIS_DOCUMENTS",
        property_condition_item=catalog_item("property_condition", "OFF_PLAN"),
    )
    assert put_resource(advisor_client, application, "property", PROPERTY).status_code == 201
    assert len(sync_calls) == 1

    same_condition = {**PROPERTY, "estimated_value_cop": 430_000_000}
    response = put_resource(advisor_client, application, "property", same_condition, '"2"')
    assert response.status_code == 200, response.content
    assert len(sync_calls) == 1

    off_plan = {**PROPERTY, "condition_code": "OFF_PLAN"}
    response = put_resource(advisor_client, application, "property", off_plan, '"3"')
    assert response.status_code == 200, response.content
    assert len(sync_calls) == 2
    assert held(application, None) == [("PROPERTY_ANALYSIS_DOCUMENTS", 1)]


def test_changing_the_purpose_resyncs(advisor_user: User, application: CreditApplication) -> None:
    requirement("REMODELING_BUDGET", purpose_item=catalog_item("loan_purpose", "HOME_IMPROVEMENT"))
    services.update_application(
        advisor_user,
        application,
        expected_version=1,
        changes={"purpose_item": catalog_item("loan_purpose", "HOME_IMPROVEMENT")},
    )

    assert held(application, None) == [("REMODELING_BUDGET", 1)]


def test_participant_changes_resync(
    advisor_user: User,
    with_product: CreditApplication,
    make_client: Callable[..., Client],
    sync_calls: list[CreditApplication],
) -> None:
    requirement("EMPLOYMENT_CERTIFICATE", participant_role=ParticipantRole.SOLIDARY_DEBTOR)
    client = make_client(document_number="80999111", first_names="Sofía")

    participant = services.add_participant(
        advisor_user, with_product, role=ParticipantRole.CO_APPLICANT, client=client
    )
    assert held(with_product, participant) == BASE_SET

    services.update_participant(
        advisor_user, participant, expected_version=2, changes={"contributes_income": False}
    )
    assert len(sync_calls) == 1

    services.update_participant(
        advisor_user,
        participant,
        expected_version=3,
        changes={"role": ParticipantRole.SOLIDARY_DEBTOR},
    )
    assert len(sync_calls) == 2
    assert held(with_product, participant) == sorted(BASE_SET + [("EMPLOYMENT_CERTIFICATE", 1)])

    services.remove_participant(advisor_user, participant)
    assert held(with_product, participant) == []

    services.add_participant(
        advisor_user, with_product, role=ParticipantRole.SOLIDARY_DEBTOR, client=client
    )
    assert held(with_product, participant) == sorted(BASE_SET + [("EMPLOYMENT_CERTIFICATE", 1)])
    assert ApplicationDocumentSlot.objects.filter(participant=participant).count() == 4


def test_the_employment_profile_resyncs_only_when_it_changes(
    advisor_client: APIClient,
    with_product: CreditApplication,
    primary: ApplicationParticipant,
    sync_calls: list[CreditApplication],
) -> None:
    from tests.applications.test_financial_profiles_api import PROFILE
    from tests.applications.test_financial_profiles_api import put as put_profile

    assert put_profile(advisor_client, primary, PROFILE).status_code == 201
    assert held(with_product, primary) == sorted(BASE_SET + EMPLOYEE_SET)
    assert len(sync_calls) == 1

    richer = {**PROFILE, "monthly_income_cop": 9_000_000}
    assert put_profile(advisor_client, primary, richer, '"2"').status_code == 200
    assert len(sync_calls) == 1

    independent = {**richer, "employment_profile_code": "INDEPENDENT", "contract_type_code": None}
    response = put_profile(advisor_client, primary, independent, '"3"')
    assert response.status_code == 200, response.content
    assert len(sync_calls) == 2
    assert held(with_product, primary) == sorted(BASE_SET + INDEPENDENT_SET)


def test_a_failed_change_leaves_the_slots_untouched(
    advisor_client: APIClient, with_product: CreditApplication
) -> None:
    sync(with_product)
    before = set(active(with_product).values_list("pk", flat=True))

    response = advisor_client.patch(
        application_url(with_product),
        {"bank_product_id": None},
        format="json",
        headers={"If-Match": '"99"'},
    )

    assert response.status_code == 409
    assert set(active(with_product).values_list("pk", flat=True)) == before
