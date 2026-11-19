"""`status_label` en usuarios e invitaciones (TAREA-brechas-3-demo, parte 1): la etiqueta
del estado sale de la API y no del front."""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.identity.models import InvitationStatus, User, UserStatus
from tests.identity.test_invitations import INVITATIONS_URL, invite
from tests.identity.test_users import USERS_URL, admin_client, admin_user, create

pytestmark = pytest.mark.django_db

__all__ = ["admin_client", "admin_user"]


def test_users_bring_the_label_of_their_status(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    inactive = make_user(email="inactivo@example.com", role_code="ADVISOR")
    inactive.is_active = False
    inactive.save()
    created = create(admin_client, email="pendiente@example.com", send_invitation=False).json()

    items = admin_client.get(USERS_URL, {"ordering": "email"}).json()["items"]

    assert [(item["status"], item["status_label"]) for item in items] == [
        ("ACTIVE", "Activo"),
        ("INACTIVE", "Inactivo"),
        ("PENDING", "Pendiente de definir contraseña"),
    ]
    assert created["status_label"] == UserStatus.PENDING.label
    detail = admin_client.get(f"{USERS_URL}/{inactive.pk}").json()
    assert detail["status_label"] == "Inactivo"


def test_invitations_bring_the_label_of_their_status(admin_client: APIClient) -> None:
    pending = invite(admin_client, email="a@example.com").json()
    revoked_id = invite(admin_client, email="b@example.com").json()["id"]
    assert admin_client.delete(f"{INVITATIONS_URL}/{revoked_id}").status_code == 204

    items = admin_client.get(INVITATIONS_URL).json()["items"]

    assert pending["status_label"] == InvitationStatus.PENDING.label
    assert {item["email"]: item["status_label"] for item in items} == {
        "a@example.com": "Pendiente",
        "b@example.com": "Revocada",
    }


def test_the_user_list_queries_do_not_grow(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(USERS_URL).status_code == 200
        return len(queries)

    make_user(email="uno@example.com", role_code="ADVISOR")
    one = measure()
    for index in range(4):
        make_user(email=f"otro{index}@example.com", role_code="ADVISOR")

    assert measure() == one
