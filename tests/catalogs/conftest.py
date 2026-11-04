import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import Catalog
from tests.helpers import login


@pytest.fixture
def admin_client(make_user) -> APIClient:
    """Administrador: la migración 0002 le asigna los permisos catalogs.* y workflow.*."""
    make_user(email="admin@example.com", role_code="ADMIN")
    client = APIClient()
    assert login(client, email="admin@example.com").status_code == 200
    return client


@pytest.fixture
def advisor_client(make_user) -> APIClient:
    make_user(email="asesor@example.com", role_code="ADVISOR")
    client = APIClient()
    assert login(client, email="asesor@example.com").status_code == 200
    return client


@pytest.fixture
def manageable_catalog(db) -> Catalog:
    return Catalog.objects.get(code="loan_purpose")


@pytest.fixture
def system_catalog(db) -> Catalog:
    return Catalog.objects.get(code="application_status")
