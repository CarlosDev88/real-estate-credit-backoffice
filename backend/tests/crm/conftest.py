from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ProjectStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership, Project
from tests.partners.conftest import client_for

CLIENTS_URL = "/api/v1/clients"
OPPORTUNITIES_URL = "/api/v1/opportunities"
BROKER_OPPORTUNITIES_URL = "/api/v1/broker/opportunities"


def catalog_item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


def client_url(client: Client | str) -> str:
    client_id = client if isinstance(client, str) else client.id
    return f"{CLIENTS_URL}/{client_id}"


def opportunity_url(opportunity: Opportunity | str) -> str:
    opportunity_id = opportunity if isinstance(opportunity, str) else opportunity.id
    return f"{OPPORTUNITIES_URL}/{opportunity_id}"


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
def other_broker(make_user: Callable[..., User]) -> User:
    return make_user(email="broker2@example.com", role_code="INDEPENDENT_BROKER")


@pytest.fixture
def admin_client(admin_user: User) -> APIClient:
    return client_for(admin_user)


@pytest.fixture
def advisor_client(advisor_user: User) -> APIClient:
    return client_for(advisor_user)


@pytest.fixture
def broker_client(broker_user: User) -> APIClient:
    return client_for(broker_user)


@pytest.fixture
def partner_client(make_user: Callable[..., User], partner: Partner) -> APIClient:
    user = make_user(email="constructora@example.com", role_code="CONSTRUCTION_PARTNER")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))
    return client_for(user)


# --- Partners y proyectos ---------------------------------------------------------------


@pytest.fixture
def partner(db: Any) -> Partner:
    return Partner.objects.create(legal_name="Constructora Andina S.A.S.", tax_id="900123456-8")


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


# --- Clientes y oportunidades -----------------------------------------------------------


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
def make_opportunity(db: Any) -> Callable[..., Opportunity]:
    def _make_opportunity(client: Client, **extra: Any) -> Opportunity:
        extra.setdefault("origin_item", catalog_item("lead_origin", "DIRECT"))
        return Opportunity.objects.create(client=client, **extra)

    return _make_opportunity
