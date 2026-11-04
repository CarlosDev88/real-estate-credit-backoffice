import re
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.models import AuthSession, InternalInvitation, User
from apps.partners.models import Partner, PartnerMembership
from tests.helpers import ME_URL, assert_error, login, role_permissions

pytestmark = pytest.mark.django_db

USERS_URL = "/api/v1/users"
NEW_PASSWORD = "Clave-Nueva-Segura-2027"


@pytest.fixture
def admin_user(make_user: Callable[..., User]) -> User:
    return make_user(email="admin@example.com", role_code="ADMIN")


@pytest.fixture
def admin_client(admin_user: User) -> APIClient:
    client = APIClient()
    assert login(client, email="admin@example.com").status_code == 200
    return client


@pytest.fixture
def partner(db: Any) -> Partner:
    return Partner.objects.create(legal_name="Constructora Andina S.A.S.", tax_id="900123456-8")


def user_url(user: User | str) -> str:
    user_id = user if isinstance(user, str) else user.id
    return f"{USERS_URL}/{user_id}"


def create(client: APIClient, **payload: Any) -> Any:
    payload = {
        "email": "Laura@Example.com",
        "first_name": "Laura",
        "last_name": "Pérez",
        "phone": "+57 300 111 2233",
        "role_codes": ["ADVISOR"],
        **payload,
    }
    with TestCase.captureOnCommitCallbacks(execute=True):
        return client.post(USERS_URL, payload)


def token_from_last_email() -> str:
    match = re.search(r"\?token=([A-Za-z0-9_\-]+)", str(mail.outbox[-1].body))
    assert match
    return match.group(1)


# --- Crear ------------------------------------------------------------------------------


def test_create_user_is_pending_and_sends_invitation(admin_client: APIClient) -> None:
    response = create(admin_client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "laura@example.com"
    assert body["name"] == "Laura Pérez"
    assert body["phone"] == "+573001112233"
    assert body["status"] == "PENDING"
    assert body["roles"] == ["ADVISOR"]
    assert body["partner"] is None
    assert body["invitation"]["status"] == "PENDING"
    assert "password" not in body

    user = User.objects.get(email="laura@example.com")
    assert not user.has_usable_password()
    assert mail.outbox[0].to == ["laura@example.com"]


def test_pending_user_accepts_invitation_and_logs_in(admin_client: APIClient) -> None:
    create(admin_client)
    response = APIClient().post(
        "/api/v1/invitations/accept",
        {
            "token": token_from_last_email(),
            "password": NEW_PASSWORD,
            "password_confirmation": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert admin_client.get(f"{USERS_URL}?status=ACTIVE&search=laura").json()["total"] == 1
    assert login(APIClient(), email="laura@example.com", password=NEW_PASSWORD).status_code == 200


def test_create_user_without_invitation(admin_client: APIClient) -> None:
    body = create(admin_client, send_invitation=False).json()
    assert body["invitation"] is None
    assert mail.outbox == []
    # Se puede invitar después.
    with TestCase.captureOnCommitCallbacks(execute=True):
        response = admin_client.post(
            "/api/v1/invitations", {"email": "laura@example.com", "role": "ADVISOR"}
        )
    assert response.status_code == 201


def test_create_partner_user_creates_membership(admin_client: APIClient, partner: Partner) -> None:
    body = create(
        admin_client, role_codes=["CONSTRUCTION_PARTNER"], partner_id=str(partner.id)
    ).json()

    assert body["partner"] == {"id": str(partner.id), "name": "Constructora Andina S.A.S."}
    assert PartnerMembership.objects.get(user__email="laura@example.com").partner == partner

    # Aceptar la invitación no duplica la membresía.
    response = APIClient().post(
        "/api/v1/invitations/accept",
        {
            "token": token_from_last_email(),
            "password": NEW_PASSWORD,
            "password_confirmation": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert PartnerMembership.objects.filter(user__email="laura@example.com").count() == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"role_codes": ["CONSTRUCTION_PARTNER"]}, "partner_id"),
        ({"role_codes": ["CONSTRUCTION_PARTNER", "ADVISOR"]}, "role_codes"),
        ({"partner_id": "PARTNER"}, "partner_id"),  # Constructora en un rol que no es partner.
        ({"role_codes": []}, "role_codes"),
        ({"role_codes": ["ADVISOR", "ADVISOR"]}, "role_codes"),
        ({"role_codes": ["BUYER"]}, "role_codes"),  # El comprador no es un usuario interno.
        ({"phone": "3001112233"}, "phone"),
        ({"first_name": ""}, "first_name"),
        ({"partner_id": str(uuid.uuid4()), "role_codes": ["CONSTRUCTION_PARTNER"]}, "partner_id"),
    ],
)
def test_create_user_validates_input(
    admin_client: APIClient, partner: Partner, payload: dict[str, Any], field: str
) -> None:
    if payload.get("partner_id") == "PARTNER":
        payload = {**payload, "partner_id": str(partner.id)}
    body = assert_error(create(admin_client, **payload), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}
    assert not User.objects.filter(email="laura@example.com").exists()


def test_email_is_unique_regardless_of_case(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    make_user(email="laura@example.com")
    assert_error(create(admin_client, email="LAURA@example.com"), 409, "EMAIL_ALREADY_REGISTERED")


def test_cannot_create_partner_user_for_inactive_partner(
    admin_client: APIClient, partner: Partner
) -> None:
    partner.status = "INACTIVE"
    partner.save()
    response = create(admin_client, role_codes=["CONSTRUCTION_PARTNER"], partner_id=str(partner.id))
    assert_error(response, 422, "PARTNER_NOT_ACTIVE")
    assert not User.objects.filter(email="laura@example.com").exists()


# --- Consultar y editar -----------------------------------------------------------------


def test_list_users_with_filters(
    admin_client: APIClient, make_user: Callable[..., User], admin_user: User
) -> None:
    make_user(email="asesor@example.com", role_code="ADVISOR")
    inactive = make_user(email="inactivo@example.com", role_code="INDEPENDENT_BROKER")
    inactive.is_active = False
    inactive.save()
    create(admin_client, email="pendiente@example.com", send_invitation=False)

    def emails(**params: Any) -> list[str]:
        items = admin_client.get(USERS_URL, {"ordering": "email", **params}).json()["items"]
        return [item["email"] for item in items]

    assert emails() == [
        "admin@example.com",
        "asesor@example.com",
        "inactivo@example.com",
        "pendiente@example.com",
    ]
    assert emails(role="ADVISOR") == ["asesor@example.com", "pendiente@example.com"]
    assert emails(status="INACTIVE") == ["inactivo@example.com"]
    assert emails(status="PENDING") == ["pendiente@example.com"]
    assert emails(status="ACTIVE") == ["admin@example.com", "asesor@example.com"]
    assert emails(search="pendi") == ["pendiente@example.com"]
    assert_error(admin_client.get(USERS_URL, {"status": "X"}), 400, "VALIDATION_ERROR")


def test_soft_deleted_users_are_hidden(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    from django.utils import timezone

    user = make_user(email="borrado@example.com")
    User.objects.filter(pk=user.pk).update(deleted_at=timezone.now())
    assert_error(admin_client.get(user_url(user)), 404, "RESOURCE_NOT_FOUND")


def test_user_detail_never_exposes_password(admin_client: APIClient, admin_user: User) -> None:
    body = admin_client.get(user_url(admin_user)).json()
    assert body["email"] == "admin@example.com"
    assert body["roles"] == ["ADMIN"]
    assert body["status"] == "ACTIVE"
    assert body["last_login"] is not None
    assert not {"password", "password_hash"} & set(body)


def test_update_user_name_and_phone(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    user = make_user(email="asesor@example.com")
    response = admin_client.patch(
        user_url(user), {"first_name": "Andrés", "phone": "+57 1 234 5678"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Andrés García"
    assert response.json()["phone"] == "+5712345678"


@pytest.mark.parametrize("payload", [{"email": "otro@example.com"}, {"is_superuser": True}])
def test_update_user_rejects_protected_fields(
    admin_client: APIClient, make_user: Callable[..., User], payload: dict[str, Any]
) -> None:
    user = make_user(email="asesor@example.com")
    assert_error(admin_client.patch(user_url(user), payload), 400, "VALIDATION_ERROR")


def test_users_require_permission(make_user: Callable[..., User]) -> None:
    make_user(email="asesor@example.com", role_code="ADVISOR")
    client = APIClient()
    login(client, email="asesor@example.com")
    assert_error(client.get(USERS_URL), 403, "PERMISSION_DENIED")
    assert_error(client.get("/api/v1/roles"), 403, "PERMISSION_DENIED")


# --- Activar y desactivar ---------------------------------------------------------------


def test_deactivate_revokes_sessions_and_pending_invitations(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    user = make_user(email="asesor@example.com", role_code="ADVISOR")
    user_client = APIClient()
    login(user_client, email="asesor@example.com")
    pending = create(admin_client, email="pendiente@example.com").json()

    url = f"{user_url(user)}/deactivate"
    assert_error(admin_client.post(url, {}), 400, "VALIDATION_ERROR")
    response = admin_client.post(url, {"reason": "Terminó el contrato"})

    assert response.status_code == 200
    assert response.json()["status"] == "INACTIVE"
    assert not AuthSession.objects.filter(user=user, revoked_at__isnull=True).exists()
    assert_error(user_client.get(ME_URL), 401, "SESSION_EXPIRED")

    admin_client.post(f"{user_url(pending['id'])}/deactivate", {"reason": "No se vinculó"})
    assert InternalInvitation.objects.get(email="pendiente@example.com").status == "REVOKED"


def test_activate_user(admin_client: APIClient, make_user: Callable[..., User]) -> None:
    user = make_user(email="asesor@example.com", is_active=False)
    response = admin_client.post(f"{user_url(user)}/activate")
    assert response.json()["status"] == "ACTIVE"
    assert login(APIClient(), email="asesor@example.com").status_code == 200


def test_admin_cannot_deactivate_self(admin_client: APIClient, admin_user: User) -> None:
    response = admin_client.post(f"{user_url(admin_user)}/deactivate", {"reason": "Prueba"})
    assert_error(response, 409, "CANNOT_MODIFY_OWN_ACCOUNT")


def test_status_change_emits_signal(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    from apps.identity.users import user_status_changed

    user = make_user(email="asesor@example.com")
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    user_status_changed.connect(handler)
    try:
        admin_client.post(f"{user_url(user)}/deactivate", {"reason": "Licencia"})
    finally:
        user_status_changed.disconnect(handler)

    assert [(r["from_status"], r["to_status"], r["reason"]) for r in received] == [
        ("ACTIVE", "INACTIVE", "Licencia")
    ]


# --- Roles ------------------------------------------------------------------------------


def test_replace_roles(
    admin_client: APIClient, make_user: Callable[..., User], admin_user: User
) -> None:
    user = make_user(email="asesor@example.com", role_code="ADVISOR")

    response = admin_client.put(
        f"{user_url(user)}/roles", {"role_codes": ["INDEPENDENT_BROKER", "ADVISOR"]}
    )

    assert response.status_code == 200
    assert sorted(response.json()["roles"]) == ["ADVISOR", "INDEPENDENT_BROKER"]
    user_client = APIClient()
    login(user_client, email="asesor@example.com")
    assert user_client.get(ME_URL).json()["roles"] == ["ADVISOR", "INDEPENDENT_BROKER"]


def test_assigning_partner_role_requires_partner_and_creates_membership(
    admin_client: APIClient, make_user: Callable[..., User], partner: Partner
) -> None:
    user = make_user(email="asesor@example.com", role_code="ADVISOR")
    url = f"{user_url(user)}/roles"

    body = assert_error(
        admin_client.put(url, {"role_codes": ["CONSTRUCTION_PARTNER"]}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == "partner_id"

    response = admin_client.put(
        url, {"role_codes": ["CONSTRUCTION_PARTNER"], "partner_id": str(partner.id)}
    )
    assert response.json()["roles"] == ["CONSTRUCTION_PARTNER"]
    assert response.json()["partner"]["id"] == str(partner.id)


def test_removing_partner_role_ends_membership(
    admin_client: APIClient, make_user: Callable[..., User], partner: Partner
) -> None:
    user = make_user(email="obra@example.com", role_code="CONSTRUCTION_PARTNER")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))

    response = admin_client.put(f"{user_url(user)}/roles", {"role_codes": ["ADVISOR"]})

    assert response.json()["partner"] is None
    membership = PartnerMembership.objects.get(user=user)
    assert membership.status == "INACTIVE"
    assert membership.ended_at is not None


def test_partner_user_cannot_be_moved_to_another_partner_via_roles(
    admin_client: APIClient, make_user: Callable[..., User], partner: Partner
) -> None:
    other = Partner.objects.create(legal_name="Otra", tax_id="901234567-7")
    user = make_user(email="obra@example.com", role_code="CONSTRUCTION_PARTNER")
    PartnerMembership.objects.create(partner=partner, user=user, started_at=date(2026, 1, 1))

    response = admin_client.put(
        f"{user_url(user)}/roles",
        {"role_codes": ["CONSTRUCTION_PARTNER"], "partner_id": str(other.id)},
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_admin_cannot_remove_own_admin_role(admin_client: APIClient, admin_user: User) -> None:
    response = admin_client.put(f"{user_url(admin_user)}/roles", {"role_codes": ["ADVISOR"]})
    assert_error(response, 409, "CANNOT_MODIFY_OWN_ACCOUNT")
    # Agregar roles sin perder ADMIN sí está permitido.
    response = admin_client.put(
        f"{user_url(admin_user)}/roles", {"role_codes": ["ADMIN", "ADVISOR"]}
    )
    assert response.status_code == 200


def test_list_roles_with_permissions(admin_client: APIClient) -> None:
    body = admin_client.get("/api/v1/roles").json()

    roles = {role["code"]: role for role in body["items"]}
    assert set(roles) == {"ADMIN", "ADVISOR", "INDEPENDENT_BROKER", "CONSTRUCTION_PARTNER"}
    admin_permissions = [permission["code"] for permission in roles["ADMIN"]["permissions"]]
    assert admin_permissions == role_permissions("ADMIN")
    assert {"users.read", "roles.assign", "invitations.create"} <= set(admin_permissions)
