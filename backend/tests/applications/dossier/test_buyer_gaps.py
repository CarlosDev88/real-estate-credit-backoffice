"""Brechas del portal y de los enlaces (TAREA-brechas-2, parte 2): `status_label` de los
consentimientos, las versiones y los enlaces, y los ingresos del comprador."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    ParticipantRole,
)
from apps.catalogs.models import CatalogItem
from apps.crm.models import Client, Opportunity
from apps.identity.models import BuyerAccessLink
from tests.applications.buyer_access.test_consents_api import consents_url
from tests.applications.buyer_access.test_links_api import links_url
from tests.applications.buyer_access.test_portal_api import buyer_application_url
from tests.applications.dossier.conftest import DocumentFileFactory, SlotFactory

pytestmark = pytest.mark.django_db


def profile(participant: ApplicationParticipant, income: int) -> FinancialProfile:
    return FinancialProfile.objects.create(
        participant=participant,
        employment_profile_item=CatalogItem.objects.get(
            catalog__code="employment_profile", code="EMPLOYEE"
        ),
        monthly_income_cop=income,
    )


# --- status_label -----------------------------------------------------------------------


def test_buyer_consents_have_a_status_label(
    buyer_client: APIClient, application: CreditApplication
) -> None:
    items = buyer_client.get(consents_url(application)).json()["items"]

    assert {(item["status"], item["status_label"]) for item in items} == {("PENDING", "Pendiente")}


def test_buyer_versions_have_a_status_label(
    portal: APIClient, make_slot: SlotFactory, make_document_file: DocumentFileFactory
) -> None:
    slot = make_slot()
    version = make_document_file(slot=slot, status="IN_REVIEW")
    slot.current_file = version
    slot.save(update_fields=["current_file"])

    items = portal.get(f"/api/v1/buyer/document-slots/{slot.pk}/versions").json()["items"]

    assert [(item["status"], item["status_label"]) for item in items] == [
        ("IN_REVIEW", "En revisión")
    ]


def test_access_links_have_a_status_label(
    advisor_client: APIClient,
    application: CreditApplication,
    make_link: Callable[..., BuyerAccessLink],
) -> None:
    make_link(revoked_at=timezone.now())
    expired = make_link()
    BuyerAccessLink.objects.filter(pk=expired.pk).update(
        created_at=timezone.now() - timedelta(hours=3),
        expires_at=timezone.now() - timedelta(hours=1),
    )

    items = advisor_client.get(links_url(application)).json()["items"]

    assert sorted((item["status"], item["status_label"]) for item in items) == [
        ("EXPIRED", "Vencido"),
        ("REVOKED", "Revocado"),
    ]


# --- Ingresos del comprador -------------------------------------------------------------


def test_income_summary_adds_the_active_participants_of_the_application(
    portal: APIClient,
    application: CreditApplication,
    primary: ApplicationParticipant,
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
) -> None:
    url = buyer_application_url(application)
    assert portal.get(url).json()["income_summary"] == {
        "participants_with_income": 0,
        "total_monthly_income_cop": 0,
    }

    co_applicant = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80123456"),
        role=ParticipantRole.CO_APPLICANT,
    )
    removed = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80123457"),
        role=ParticipantRole.CO_APPLICANT,
        is_active=False,
    )
    no_income = ApplicationParticipant.objects.create(
        application=application,
        client=make_client(document_number="80123458"),
        role=ParticipantRole.SOLIDARY_DEBTOR,
    )
    profile(primary, 5_000_000)
    profile(co_applicant, 3_000_000)
    profile(removed, 9_000_000)
    profile(no_income, 0)
    # El mismo comprador en otra solicitud: no cuenta.
    other = make_application(make_opportunity(application.opportunity.client))
    profile(other.participants.get(role=ParticipantRole.PRIMARY), 7_000_000)

    assert portal.get(url).json()["income_summary"] == {
        "participants_with_income": 2,
        "total_monthly_income_cop": 8_000_000,
    }
