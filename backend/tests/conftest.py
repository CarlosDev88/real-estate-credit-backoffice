import warnings
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.documents.storage import MemoryStorage, get_storage
from apps.identity.models import Permission, Role, RolePermission, User, UserRole
from scripts.ci_report import WarningRecorder
from tests.helpers import DEFAULT_PASSWORD, login

# En CI (CI_REPORT_DIR definida) se guardan los warnings para el reporte del PR.
_warning_recorder = WarningRecorder.from_env()


def pytest_warning_recorded(
    warning_message: warnings.WarningMessage, when: str, nodeid: str
) -> None:
    if _warning_recorder is not None:
        _warning_recorder.record(warning_message, nodeid=nodeid, when=when)


def pytest_sessionfinish() -> None:
    if _warning_recorder is not None:
        _warning_recorder.write()


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Los límites de consumo viven en la caché; cada prueba empieza en cero."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _clear_document_storage() -> Iterator[None]:
    """El almacenamiento en memoria es uno por proceso; cada prueba empieza vacía."""
    yield
    storage = get_storage()
    if isinstance(storage, MemoryStorage):
        storage.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def csrf_client() -> APIClient:
    """Cliente que, como un navegador real, está sujeto a la validación CSRF."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def make_user(db: Any) -> Callable[..., User]:
    def _make_user(
        email: str = "asesor@example.com",
        password: str = DEFAULT_PASSWORD,
        role_code: str | None = "ADVISOR",
        permissions: list[str] | None = None,
        **extra: Any,
    ) -> User:
        extra.setdefault("first_name", "Andrea")
        extra.setdefault("last_name", "García")
        user = User.objects.create_user(email=email, password=password, **extra)
        if role_code:
            role = Role.objects.get(code=role_code)
            UserRole.objects.create(user=user, role=role)
            for code in permissions or []:
                permission, _ = Permission.objects.get_or_create(
                    code=code,
                    defaults={"module": code.split(".")[0], "name": code},
                )
                RolePermission.objects.get_or_create(role=role, permission=permission)
        return user

    return _make_user


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user(permissions=["applications.read_assigned", "documents.review"])


@pytest.fixture
def logged_client(api_client: APIClient, user: User) -> APIClient:
    response = login(api_client)
    assert response.status_code == 200, response.content
    return api_client
