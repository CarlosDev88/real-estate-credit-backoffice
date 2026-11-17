"""Etiquetas para el portal: estado público del slot, ``needs_action`` y ``role_label``."""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents.models import (
    ACTIONABLE_PUBLIC_STATUSES,
    PUBLIC_SLOT_STATUS,
    PublicSlotStatus,
    SlotStatus,
)
from tests.applications.buyer_access.conftest import set_status
from tests.applications.conftest import application_url, catalog_item
from tests.applications.dossier.conftest import SlotFactory

pytestmark = pytest.mark.django_db

ROLE_LABELS = {
    "PRIMARY": "Titular",
    "CO_APPLICANT": "Co-solicitante",
    "SOLIDARY_DEBTOR": "Deudor solidario",
}


def buyer_slots_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}/document-slots"


def test_every_slot_status_has_a_public_status() -> None:
    assert set(PUBLIC_SLOT_STATUS) == set(SlotStatus.values)
    assert set(PUBLIC_SLOT_STATUS.values()) == set(PublicSlotStatus)
    assert set(ACTIONABLE_PUBLIC_STATUSES) == {PublicSlotStatus.TO_UPLOAD, PublicSlotStatus.TO_FIX}


@pytest.mark.parametrize(
    ("status", "public_status", "label", "needs_action"),
    [
        (SlotStatus.PENDING, "TO_UPLOAD", "Te falta", True),
        (SlotStatus.REJECTED, "TO_FIX", "Corrígelo", True),
        (SlotStatus.UPLOADED, "IN_REVIEW", "En revisión", False),
        (SlotStatus.APPROVED, "DONE", "Listo", False),
        (SlotStatus.WAIVED, "NOT_APPLICABLE", "No aplica", False),
    ],
)
def test_the_buyer_slot_carries_its_public_status(
    portal: APIClient,
    application: CreditApplication,
    make_slot: SlotFactory,
    status: str,
    public_status: str,
    label: str,
    needs_action: bool,
) -> None:
    extra = {}
    if status == SlotStatus.WAIVED:
        extra = {
            "is_waivable": True,
            "waiver_reason_item": catalog_item("document_waiver_reason", "NOT_APPLICABLE"),
        }
    make_slot(status=status, **extra)

    (row,) = portal.get(buyer_slots_url(application)).json()["items"]

    assert row["status"] == status
    assert row["public_status"] == public_status
    assert row["public_status_label"] == label
    assert row["needs_action"] is needs_action


def test_needs_action_is_false_when_the_slot_does_not_accept_an_upload(
    portal: APIClient, application: CreditApplication, make_slot: SlotFactory
) -> None:
    """Después de radicar, un rechazado sin observación del banco no admite carga."""
    make_slot(status=SlotStatus.REJECTED)
    set_status(application, ApplicationStatus.FILED)

    (row,) = portal.get(buyer_slots_url(application)).json()["items"]

    assert row["public_status"] == "TO_FIX"
    assert row["can_upload"] is False
    assert row["needs_action"] is False


@pytest.fixture
def participants(
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
) -> list[ApplicationParticipant]:
    """Titular, co-solicitante y deudor solidario, todos con un slot."""
    co_applicant = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="1032445909", first_names="Mario"),
        role=ParticipantRole.CO_APPLICANT,
    )
    solidary = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="1032445910", first_names="Rosa"),
        role=ParticipantRole.SOLIDARY_DEBTOR,
    )
    return [primary, co_applicant, solidary]


def _labels(rows: list[dict[str, str]]) -> dict[str, str]:
    return {row["role"]: row["role_label"] for row in rows}


def test_role_label_in_every_buyer_dto(
    portal: APIClient,
    application: CreditApplication,
    participants: list[ApplicationParticipant],
    make_slot: SlotFactory,
) -> None:
    for participant in participants:
        make_slot(participant=participant)

    detail = portal.get(f"/api/v1/buyer/applications/{application.pk}").json()
    summary = portal.get(f"/api/v1/buyer/applications/{application.pk}/participants").json()[
        "items"
    ]
    slots = portal.get(buyer_slots_url(application)).json()["items"]

    assert _labels(detail["participants"]) == ROLE_LABELS
    assert _labels(summary) == ROLE_LABELS
    assert _labels([row["participant"] for row in slots]) == ROLE_LABELS


def test_role_label_in_the_internal_participants_and_slots(
    admin_client: APIClient,
    application: CreditApplication,
    participants: list[ApplicationParticipant],
    make_slot: SlotFactory,
) -> None:
    for participant in participants:
        make_slot(participant=participant)

    listed = admin_client.get(application_url(application, "/participants")).json()["items"]
    slots = admin_client.get(application_url(application, "/document-slots")).json()["items"]

    assert _labels(listed) == ROLE_LABELS
    assert _labels([row["participant"] for row in slots]) == ROLE_LABELS
