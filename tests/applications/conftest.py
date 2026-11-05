from collections.abc import Callable
from typing import Any

import pytest

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    ParticipantRole,
    next_application_code,
)
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import OpportunityStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


# --- Usuarios ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(make_user: Callable[..., User]) -> User:
    return make_user(email="admin@example.com", role_code="ADMIN")


@pytest.fixture
def advisor_user(make_user: Callable[..., User]) -> User:
    return make_user(email="asesor@example.com", role_code="ADVISOR")


# --- Clientes, oportunidades y solicitudes ----------------------------------------------


@pytest.fixture
def make_client(db: Any) -> Callable[..., Client]:
    def _make_client(**extra: Any) -> Client:
        extra.setdefault("document_type_item", catalog_item("identity_document_type", "CC"))
        extra.setdefault("document_number", "1032445908")
        extra.setdefault("first_names", "Laura")
        extra.setdefault("last_names", "Gómez Vélez")
        return Client.objects.create(**extra)

    return _make_client


@pytest.fixture
def buyer(make_client: Callable[..., Client]) -> Client:
    return make_client()


@pytest.fixture
def opportunity(buyer: Client, advisor_user: User) -> Opportunity:
    return Opportunity.objects.create(
        client=buyer,
        origin_item=catalog_item("lead_origin", "DIRECT"),
        assigned_advisor=advisor_user,
        status=OpportunityStatus.ASSIGNED,
    )


@pytest.fixture
def make_application(advisor_user: User) -> Callable[..., CreditApplication]:
    """Solicitud creada directamente en la base, sin pasar por los servicios."""

    def _make_application(opportunity: Opportunity, **extra: Any) -> CreditApplication:
        extra.setdefault("code", next_application_code())
        extra.setdefault("purpose_item", catalog_item("loan_purpose", "PURCHASE_NEW"))
        extra.setdefault("assigned_advisor", advisor_user)
        return CreditApplication.objects.create(opportunity=opportunity, **extra)

    return _make_application


@pytest.fixture
def application(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity
) -> CreditApplication:
    return make_application(opportunity)


@pytest.fixture
def primary(application: CreditApplication, buyer: Client) -> ApplicationParticipant:
    return ApplicationParticipant.objects.create(
        application=application, client=buyer, role=ParticipantRole.PRIMARY
    )
