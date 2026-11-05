from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    ParticipantRole,
    next_application_code,
)
from apps.banking.models import Bank, BankProduct, BankProductPurpose
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import OpportunityStatus, ProjectStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership, Project
from tests.partners.conftest import client_for

APPLICATIONS_URL = "/api/v1/applications"


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


def application_url(application: CreditApplication | str, suffix: str = "") -> str:
    application_id = application if isinstance(application, str) else application.id
    return f"{APPLICATIONS_URL}/{application_id}{suffix}"


def seeded_product(bank_code: str = "BANCOLOMBIA") -> BankProduct:
    """Producto sembrado: admite las tres finalidades del MVP."""
    return BankProduct.objects.get(bank__code=bank_code, code="MORTGAGE")


# --- Usuarios ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(make_user: Callable[..., User]) -> User:
    return make_user(email="admin@example.com", role_code="ADMIN")


@pytest.fixture
def advisor_user(make_user: Callable[..., User]) -> User:
    return make_user(email="asesor@example.com", role_code="ADVISOR")


@pytest.fixture
def other_advisor(make_user: Callable[..., User]) -> User:
    return make_user(email="asesora2@example.com", role_code="ADVISOR", first_name="Marta")


@pytest.fixture
def broker_user(make_user: Callable[..., User]) -> User:
    return make_user(email="broker@example.com", role_code="INDEPENDENT_BROKER")


@pytest.fixture
def admin_client(admin_user: User) -> APIClient:
    return client_for(admin_user)


@pytest.fixture
def advisor_client(advisor_user: User) -> APIClient:
    return client_for(advisor_user)


@pytest.fixture
def other_advisor_client(other_advisor: User) -> APIClient:
    return client_for(other_advisor)


@pytest.fixture
def broker_client(broker_user: User) -> APIClient:
    return client_for(broker_user)


@pytest.fixture
def partner(db: Any) -> Partner:
    return Partner.objects.create(legal_name="Constructora Andina S.A.S.", tax_id="900123456-8")


@pytest.fixture
def partner_client(make_user: Callable[..., User], partner: Partner) -> APIClient:
    user = make_user(email="constructora@example.com", role_code="CONSTRUCTION_PARTNER")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))
    return client_for(user)


# --- Proyectos y productos --------------------------------------------------------------


@pytest.fixture
def make_project(partner: Partner, admin_user: User) -> Callable[..., Project]:
    def _make_project(**extra: Any) -> Project:
        extra.setdefault("name", "Verona 118")
        extra.setdefault("address", "Carrera 11 # 118-40")
        extra.setdefault("status", ProjectStatus.ACTIVE)
        extra.setdefault("city_item", catalog_item("municipality", "11001"))
        extra.setdefault("created_by", admin_user)
        return Project.objects.create(partner=partner, **extra)

    return _make_project


@pytest.fixture
def active_project(make_project: Callable[..., Project]) -> Project:
    return make_project()


@pytest.fixture
def new_home_only_product(db: Any) -> BankProduct:
    """Producto que solo admite compra de vivienda nueva."""
    bank = Bank.objects.create(code="BANCO_PRUEBA", name="Banco de Prueba")
    product = BankProduct.objects.create(
        bank=bank,
        code="MORTGAGE",
        name="Hipotecario vivienda nueva",
        product_type_item=catalog_item("bank_product_type", "MORTGAGE"),
        valid_from=date(2026, 1, 1),
    )
    BankProductPurpose.objects.create(
        bank_product=product, purpose_item=catalog_item("loan_purpose", "PURCHASE_NEW")
    )
    return product


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
def make_opportunity(advisor_user: User) -> Callable[..., Opportunity]:
    def _make_opportunity(client: Client, **extra: Any) -> Opportunity:
        extra.setdefault("origin_item", catalog_item("lead_origin", "DIRECT"))
        extra.setdefault("assigned_advisor", advisor_user)
        extra.setdefault("status", OpportunityStatus.ASSIGNED)
        return Opportunity.objects.create(client=client, **extra)

    return _make_opportunity


@pytest.fixture
def opportunity(make_opportunity: Callable[..., Opportunity], buyer: Client) -> Opportunity:
    return make_opportunity(buyer)


@pytest.fixture
def make_application(advisor_user: User) -> Callable[..., CreditApplication]:
    """Solicitud creada directamente en la base, sin pasar por los servicios."""

    def _make_application(opportunity: Opportunity, **extra: Any) -> CreditApplication:
        extra.setdefault("code", next_application_code())
        extra.setdefault("purpose_item", catalog_item("loan_purpose", "PURCHASE_NEW"))
        extra.setdefault("assigned_advisor", advisor_user)
        application = CreditApplication.objects.create(opportunity=opportunity, **extra)
        ApplicationParticipant.objects.create(
            application=application, client=opportunity.client, role=ParticipantRole.PRIMARY
        )
        return application

    return _make_application


@pytest.fixture
def application(
    make_application: Callable[..., CreditApplication], opportunity: Opportunity
) -> CreditApplication:
    return make_application(opportunity)


@pytest.fixture
def primary(application: CreditApplication) -> ApplicationParticipant:
    return application.participants.get(role=ParticipantRole.PRIMARY)
