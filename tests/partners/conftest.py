from collections.abc import Callable
from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import ProjectStatus
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership, Project
from tests.helpers import login


def client_for(user: User) -> APIClient:
    client = APIClient()
    assert login(client, email=user.email).status_code == 200
    return client


@pytest.fixture
def make_partner(db) -> Callable[..., Partner]:
    def _make_partner(**extra) -> Partner:
        extra.setdefault("legal_name", "Constructora Andina S.A.S.")
        extra.setdefault("tax_id", "900123456-8")
        return Partner.objects.create(**extra)

    return _make_partner


@pytest.fixture
def partner(make_partner) -> Partner:
    return make_partner()


@pytest.fixture
def other_partner(make_partner) -> Partner:
    return make_partner(legal_name="Constructora del Valle S.A.S.", tax_id="901234567-7")


@pytest.fixture
def bogota(db) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code="municipality", code="11001")


@pytest.fixture
def medellin(db) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code="municipality", code="05001")


@pytest.fixture
def admin_user(make_user) -> User:
    return make_user(email="admin@example.com", role_code="ADMIN")


@pytest.fixture
def advisor_user(make_user) -> User:
    return make_user(email="asesor@example.com", role_code="ADVISOR")


@pytest.fixture
def broker_user(make_user) -> User:
    return make_user(email="broker@example.com", role_code="INDEPENDENT_BROKER")


@pytest.fixture
def partner_user(make_user, partner) -> User:
    user = make_user(email="constructora@example.com", role_code="CONSTRUCTION_PARTNER")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))
    return user


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    return client_for(admin_user)


@pytest.fixture
def advisor_client(advisor_user) -> APIClient:
    return client_for(advisor_user)


@pytest.fixture
def broker_client(broker_user) -> APIClient:
    return client_for(broker_user)


@pytest.fixture
def partner_client(partner_user) -> APIClient:
    return client_for(partner_user)


@pytest.fixture
def make_project(bogota, admin_user) -> Callable[..., Project]:
    def _make_project(partner: Partner, **extra) -> Project:
        extra.setdefault("name", "Verona 118")
        extra.setdefault("address", "Carrera 11 # 118-40")
        extra.setdefault("status", ProjectStatus.DRAFT)
        extra.setdefault("city_item", bogota)
        extra.setdefault("created_by", admin_user)
        return Project.objects.create(partner=partner, **extra)

    return _make_project
