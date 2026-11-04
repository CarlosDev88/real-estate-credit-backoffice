import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.identity.models import InternalInvitation, User, UserRole
from apps.identity.tokens import hash_token
from apps.partners.models import Partner, PartnerMembership
from tests.helpers import DEFAULT_PASSWORD, assert_error, login

pytestmark = pytest.mark.django_db

INVITATIONS_URL = "/api/v1/invitations"
ACCEPT_URL = "/api/v1/invitations/accept"
NEW_PASSWORD = "Clave-Nueva-Segura-2027"


@pytest.fixture
def admin_client(make_user: Callable[..., User]) -> APIClient:
    make_user(email="admin@example.com", role_code="ADMIN")
    client = APIClient()
    assert login(client, email="admin@example.com").status_code == 200
    return client


@pytest.fixture
def partner(db: Any) -> Partner:
    return Partner.objects.create(legal_name="Constructora Andina S.A.S.", tax_id="900123456-8")


def invite(client: APIClient, **payload: Any) -> Any:
    payload.setdefault("email", "nuevo@example.com")
    payload.setdefault("role", "ADVISOR")
    # El correo se envía en `on_commit`, y en pruebas la transacción nunca confirma.
    with TestCase.captureOnCommitCallbacks(execute=True):
        return client.post(INVITATIONS_URL, payload)


def four_days_ago() -> datetime:
    """Más que la vigencia de 72 horas, relativo a hoy."""
    return timezone.now() - timedelta(days=4)


def invite_at(moment: datetime, email: str = "nuevo@example.com") -> InternalInvitation:
    """Crea la invitación con el servicio en una fecha pasada.

    Por API no sirve: con el reloj en el pasado, el JWT del admin todavía no es válido.
    """
    from apps.identity.invitations import create_invitation
    from apps.identity.models import Role

    admin = User.objects.get(email="admin@example.com")
    with freeze_time(moment), TestCase.captureOnCommitCallbacks(execute=True):
        return create_invitation(
            email=email, role=Role.objects.get(code="ADVISOR"), partner=None, invited_by=admin
        )


def token_from_last_email() -> str:
    match = re.search(r"\?token=([A-Za-z0-9_\-]+)", str(mail.outbox[-1].body))
    assert match, mail.outbox[-1].body
    return match.group(1)


def accept(token: str, **payload: Any) -> Any:
    payload = {
        "token": token,
        "password": NEW_PASSWORD,
        "password_confirmation": NEW_PASSWORD,
        "first_name": "Laura",
        "last_name": "Pérez",
        **payload,
    }
    return APIClient().post(ACCEPT_URL, payload)


# --- Crear ------------------------------------------------------------------------------


def test_admin_invites_internal_user(admin_client: APIClient) -> None:
    response = invite(admin_client, email="Nuevo@Example.com")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "nuevo@example.com"
    assert body["role"] == "ADVISOR"
    assert body["status"] == "PENDING"
    assert body["partner"] is None
    assert body["invited_by"]["name"] == "Andrea García"
    assert "token" not in body and "token_hash" not in body

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["nuevo@example.com"]
    assert "http://localhost:3000/aceptar-invitacion?token=" in mail.outbox[0].body
    invitation = InternalInvitation.objects.get()
    assert invitation.token_hash == hash_token(token_from_last_email())
    lifetime = invitation.expires_at - invitation.created_at
    assert abs(lifetime - timedelta(hours=72)) < timedelta(seconds=5)


def test_partner_invitation_requires_partner(admin_client: APIClient, partner: Partner) -> None:
    body = assert_error(invite(admin_client, role="CONSTRUCTION_PARTNER"), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "partner_id"

    response = invite(admin_client, role="CONSTRUCTION_PARTNER", partner_id=str(partner.id))
    assert response.status_code == 201
    assert response.json()["partner"]["id"] == str(partner.id)
    assert "Te unirás al equipo de" in mail.outbox[-1].body


def test_only_partner_invitations_carry_a_partner(
    admin_client: APIClient, partner: Partner
) -> None:
    response = invite(admin_client, role="ADVISOR", partner_id=str(partner.id))
    assert_error(response, 400, "VALIDATION_ERROR")


def test_cannot_invite_to_inactive_partner(admin_client: APIClient, partner: Partner) -> None:
    partner.status = "INACTIVE"
    partner.save()
    response = invite(admin_client, role="CONSTRUCTION_PARTNER", partner_id=str(partner.id))
    assert_error(response, 422, "PARTNER_NOT_ACTIVE")


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "SUPERHERO"},
        {"email": "no-es-correo"},
        {"partner_id": str(uuid.uuid4()), "role": "CONSTRUCTION_PARTNER"},
        {"is_superuser": True},
    ],
)
def test_create_invitation_validates_input(
    admin_client: APIClient, payload: dict[str, Any]
) -> None:
    assert_error(invite(admin_client, **payload), 400, "VALIDATION_ERROR")


def test_cannot_invite_an_existing_account(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    make_user(email="existente@example.com")
    response = invite(admin_client, email="EXISTENTE@example.com")
    assert_error(response, 409, "USER_ALREADY_EXISTS")


def test_only_one_pending_invitation_per_email(admin_client: APIClient) -> None:
    invite(admin_client)
    assert_error(invite(admin_client, role="ADMIN"), 409, "INVITATION_ALREADY_PENDING")


def test_invitations_require_permission(make_user: Callable[..., User]) -> None:
    make_user(email="asesor@example.com", role_code="ADVISOR")
    client = APIClient()
    login(client, email="asesor@example.com")
    assert_error(invite(client), 403, "PERMISSION_DENIED")
    assert_error(client.get(INVITATIONS_URL), 403, "PERMISSION_DENIED")


# --- Aceptar ----------------------------------------------------------------------------


def test_accept_creates_user_with_role_and_allows_login(admin_client: APIClient) -> None:
    invite(admin_client)

    response = accept(token_from_last_email())

    assert response.status_code == 200
    assert response.json()["email"] == "nuevo@example.com"
    assert response.json()["name"] == "Laura Pérez"
    assert response.json()["roles"] == ["ADVISOR"]

    user = User.objects.get(email="nuevo@example.com")
    assert user.is_active
    assert user.check_password(NEW_PASSWORD)
    assert UserRole.objects.get(user=user).role.code == "ADVISOR"
    assert InternalInvitation.objects.get().status == "ACCEPTED"

    assert login(APIClient(), email="nuevo@example.com", password=NEW_PASSWORD).status_code == 200


def test_accept_partner_invitation_creates_membership(
    admin_client: APIClient, partner: Partner
) -> None:
    invite(admin_client, role="CONSTRUCTION_PARTNER", partner_id=str(partner.id))

    assert accept(token_from_last_email()).status_code == 200

    membership = PartnerMembership.objects.get(user__email="nuevo@example.com")
    assert membership.partner == partner
    assert membership.status == "ACTIVE"


def test_accept_links_an_existing_user_without_password(admin_client: APIClient) -> None:
    pending = User.objects.create_user(
        email="pendiente@example.com", password=None, first_name="Ana", last_name="Ruiz"
    )
    pending.is_active = False
    pending.save()
    invite(admin_client, email="pendiente@example.com")

    # Los nombres ya existen, así que no son obligatorios.
    response = accept(token_from_last_email(), first_name="", last_name="")

    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.is_active
    assert pending.check_password(NEW_PASSWORD)
    assert pending.get_full_name() == "Ana Ruiz"
    assert User.objects.filter(email="pendiente@example.com").count() == 1


def test_accept_requires_names_for_new_users(admin_client: APIClient) -> None:
    invite(admin_client)
    body = assert_error(
        accept(token_from_last_email(), first_name="", last_name=""), 400, "VALIDATION_ERROR"
    )
    assert {detail["field"] for detail in body["details"]} == {"first_name", "last_name"}


def test_accept_is_single_use(admin_client: APIClient) -> None:
    invite(admin_client)
    token = token_from_last_email()
    assert accept(token).status_code == 200
    assert_error(accept(token), 400, "INVITATION_INVALID")


def test_accept_rejects_expired_invitations(admin_client: APIClient) -> None:
    invite_at(four_days_ago())
    assert_error(accept(token_from_last_email()), 400, "INVITATION_INVALID")


def test_accept_rejects_unknown_token(db: Any) -> None:
    assert_error(accept("token-inventado"), 400, "INVITATION_INVALID")


def test_accept_validates_passwords(admin_client: APIClient) -> None:
    invite(admin_client)
    token = token_from_last_email()

    body = assert_error(accept(token, password_confirmation="otra-cosa"), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "password_confirmation"

    body = assert_error(
        accept(token, password="12345678", password_confirmation="12345678"),
        400,
        "VALIDATION_ERROR",
    )
    assert body["details"][0]["field"] == "password"

    # Los errores no consumen la invitación.
    assert accept(token).status_code == 200


def test_accept_fails_if_partner_was_deactivated(admin_client: APIClient, partner: Partner) -> None:
    invite(admin_client, role="CONSTRUCTION_PARTNER", partner_id=str(partner.id))
    partner.status = "INACTIVE"
    partner.save()

    assert_error(accept(token_from_last_email()), 422, "PARTNER_NOT_ACTIVE")
    assert not User.objects.filter(email="nuevo@example.com").exists()


def test_accept_cannot_take_over_an_account_created_meanwhile(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    invite(admin_client)
    make_user(email="nuevo@example.com", password=DEFAULT_PASSWORD)

    assert_error(accept(token_from_last_email()), 409, "USER_ALREADY_EXISTS")
    user = User.objects.get(email="nuevo@example.com")
    assert user.check_password(DEFAULT_PASSWORD)


def test_accept_is_rate_limited(db: Any) -> None:
    for _ in range(10):
        accept("token-inventado")
    assert_error(accept("token-inventado"), 429, "RATE_LIMITED")


# --- Reenviar, revocar y listar ---------------------------------------------------------


def test_resend_revokes_previous_token(admin_client: APIClient) -> None:
    invitation_id = invite(admin_client).json()["id"]
    old_token = token_from_last_email()

    with TestCase.captureOnCommitCallbacks(execute=True):
        response = admin_client.post(f"{INVITATIONS_URL}/{invitation_id}/resend")

    assert response.status_code == 201
    assert response.json()["id"] != invitation_id
    assert response.json()["status"] == "PENDING"
    assert len(mail.outbox) == 2
    assert InternalInvitation.objects.get(pk=invitation_id).status == "REVOKED"

    assert_error(accept(old_token), 400, "INVITATION_INVALID")
    assert accept(token_from_last_email()).status_code == 200


def test_resend_works_for_expired_invitations(admin_client: APIClient) -> None:
    invitation_id = invite_at(four_days_ago()).id
    response = admin_client.post(f"{INVITATIONS_URL}/{invitation_id}/resend")
    assert response.status_code == 201


def test_cannot_resend_accepted_invitation(admin_client: APIClient) -> None:
    invitation_id = invite(admin_client).json()["id"]
    accept(token_from_last_email())

    response = admin_client.post(f"{INVITATIONS_URL}/{invitation_id}/resend")
    assert_error(response, 409, "INVITATION_NOT_PENDING")
    assert_error(
        admin_client.delete(f"{INVITATIONS_URL}/{invitation_id}"), 409, "INVITATION_NOT_PENDING"
    )


def test_revoke_invitation(admin_client: APIClient) -> None:
    invitation_id = invite(admin_client).json()["id"]
    token = token_from_last_email()

    assert admin_client.delete(f"{INVITATIONS_URL}/{invitation_id}").status_code == 204
    assert admin_client.delete(f"{INVITATIONS_URL}/{invitation_id}").status_code == 204
    assert_error(accept(token), 400, "INVITATION_INVALID")
    # Revocar libera el correo para una invitación nueva.
    assert invite(admin_client).status_code == 201


def test_unknown_invitation_returns_404(admin_client: APIClient) -> None:
    assert_error(
        admin_client.delete(f"{INVITATIONS_URL}/{uuid.uuid4()}"), 404, "RESOURCE_NOT_FOUND"
    )


def test_list_invitations_with_filters(admin_client: APIClient, partner: Partner) -> None:
    invite(admin_client, email="a@example.com")
    invite(
        admin_client, email="b@example.com", role="CONSTRUCTION_PARTNER", partner_id=str(partner.id)
    )
    revoked_id = invite(admin_client, email="c@example.com").json()["id"]
    admin_client.delete(f"{INVITATIONS_URL}/{revoked_id}")

    def emails(**params: Any) -> list[str]:
        return [item["email"] for item in admin_client.get(INVITATIONS_URL, params).json()["items"]]

    assert emails() == ["c@example.com", "b@example.com", "a@example.com"]
    assert emails(status="PENDING") == ["b@example.com", "a@example.com"]
    assert emails(status="REVOKED") == ["c@example.com"]
    assert emails(role="CONSTRUCTION_PARTNER") == ["b@example.com"]
    assert emails(partner_id=str(partner.id)) == ["b@example.com"]
    assert emails(email="A@EXAMPLE.COM") == ["a@example.com"]
    assert_error(admin_client.get(INVITATIONS_URL, {"status": "X"}), 400, "VALIDATION_ERROR")


def test_expired_status_is_derived_from_dates(admin_client: APIClient) -> None:
    invitation_id = str(invite_at(four_days_ago()).id)
    items = admin_client.get(INVITATIONS_URL, {"status": "EXPIRED"}).json()["items"]
    assert [item["id"] for item in items] == [invitation_id]
    # Una invitación vencida no bloquea una nueva.
    assert invite(admin_client).status_code == 201


# --- Invitar desde la constructora ------------------------------------------------------


def test_partner_members_endpoint_can_invite_by_email(
    admin_client: APIClient, partner: Partner
) -> None:
    with TestCase.captureOnCommitCallbacks(execute=True):
        response = admin_client.post(
            f"/api/v1/partners/{partner.id}/members", {"email": "obra@example.com"}
        )

    assert response.status_code == 202
    assert response.json()["role"] == "CONSTRUCTION_PARTNER"
    assert response.json()["partner"]["id"] == str(partner.id)

    accept(token_from_last_email())
    assert PartnerMembership.objects.filter(
        partner=partner, user__email="obra@example.com"
    ).exists()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "obra@example.com", "user_id": str(uuid.uuid4())},
        {"email": "obra@example.com", "job_title": "Gerente"},
    ],
)
def test_partner_members_endpoint_validates_mode(
    admin_client: APIClient, partner: Partner, payload: dict[str, Any]
) -> None:
    response = admin_client.post(f"/api/v1/partners/{partner.id}/members", payload)
    assert_error(response, 400, "VALIDATION_ERROR")
