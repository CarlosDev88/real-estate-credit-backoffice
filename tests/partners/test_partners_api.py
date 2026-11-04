import uuid
from datetime import date

import pytest

from apps.partners.models import Partner, PartnerMembership
from tests.helpers import ME_URL, assert_error
from tests.partners.conftest import client_for

pytestmark = pytest.mark.django_db

PARTNERS_URL = "/api/v1/partners"


def partner_url(partner: Partner) -> str:
    return f"{PARTNERS_URL}/{partner.id}"


VALID_PARTNER = {
    "legal_name": "Constructora Bolívar S.A.",
    "trade_name": "Bolívar",
    "tax_id": "860.002.964-4",
    "contact_name": "Laura Pérez",
    "contact_email": "Laura@Constructora.COM",
    "contact_phone": "+57 300 123 4567",
}


# --- Crear y editar ---------------------------------------------------------------------


def test_admin_creates_partner_with_normalized_data(admin_client):
    response = admin_client.post(PARTNERS_URL, VALID_PARTNER)

    assert response.status_code == 201
    body = response.json()
    assert body["tax_id"] == "860002964-4"
    assert body["contact_email"] == "laura@constructora.com"
    assert body["contact_phone"] == "+573001234567"
    assert body["status"] == "ACTIVE"


def test_partner_tax_id_is_unique(admin_client, partner):
    response = admin_client.post(PARTNERS_URL, {**VALID_PARTNER, "tax_id": "900.123.456-8"})
    assert_error(response, 409, "DUPLICATE_TAX_ID")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tax_id", "860002964-1"),
        ("tax_id", "860002964"),
        ("contact_phone", "3001234567"),
        ("contact_email", "no-es-correo"),
    ],
)
def test_partner_validates_input(admin_client, field, value):
    body = assert_error(
        admin_client.post(PARTNERS_URL, {**VALID_PARTNER, field: value}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == field


def test_only_admin_creates_partners(advisor_client, partner_client):
    for client in (advisor_client, partner_client):
        assert_error(client.post(PARTNERS_URL, VALID_PARTNER), 403, "PERMISSION_DENIED")


def test_update_partner_contact(admin_client, partner):
    response = admin_client.patch(partner_url(partner), {"contact_name": "Nuevo contacto"})
    assert response.status_code == 200
    assert response.json()["contact_name"] == "Nuevo contacto"


def test_partner_tax_id_cannot_be_changed(admin_client, partner):
    response = admin_client.patch(partner_url(partner), {"tax_id": "901234567-7"})
    assert_error(response, 400, "VALIDATION_ERROR")


# --- Consultar --------------------------------------------------------------------------


def test_admin_and_advisor_list_all_partners(admin_client, advisor_client, partner, other_partner):
    for client in (admin_client, advisor_client):
        body = client.get(PARTNERS_URL).json()
        assert body["total"] == 2


def test_partner_user_only_sees_own_partner(partner_client, partner, other_partner):
    body = partner_client.get(PARTNERS_URL).json()
    assert [item["id"] for item in body["items"]] == [str(partner.id)]

    assert partner_client.get(partner_url(partner)).status_code == 200
    # Otra constructora responde 404: no se confirma que exista.
    assert_error(partner_client.get(partner_url(other_partner)), 404, "RESOURCE_NOT_FOUND")


def test_broker_cannot_read_partners(broker_client, partner):
    assert_error(broker_client.get(PARTNERS_URL), 403, "PERMISSION_DENIED")


def test_partner_detail_includes_metrics(admin_client, partner, partner_user, make_project):
    make_project(partner)
    make_project(partner, name="Torre Norte", status="ACTIVE")

    body = admin_client.get(partner_url(partner)).json()
    assert body["metrics"]["active_members"] == 1
    assert body["metrics"]["projects_by_status"] == {
        "DRAFT": 1,
        "PENDING_REVIEW": 0,
        "ACTIVE": 1,
        "ARCHIVED": 0,
    }


def test_list_partners_filters(admin_client, partner, other_partner, make_project, medellin):
    other_partner.status = "INACTIVE"
    other_partner.save()
    make_project(partner, city_item=medellin)

    assert admin_client.get(PARTNERS_URL, {"status": "INACTIVE"}).json()["total"] == 1
    body = admin_client.get(PARTNERS_URL, {"city_code": "05001"}).json()
    assert [item["id"] for item in body["items"]] == [str(partner.id)]
    assert admin_client.get(PARTNERS_URL, {"search": "Valle"}).json()["total"] == 1
    assert_error(admin_client.get(PARTNERS_URL, {"status": "X"}), 400, "VALIDATION_ERROR")


def test_soft_deleted_partners_are_hidden(admin_client, partner):
    from django.utils import timezone

    Partner.objects.filter(pk=partner.pk).update(deleted_at=timezone.now())
    assert admin_client.get(PARTNERS_URL).json()["total"] == 0
    assert_error(admin_client.get(partner_url(partner)), 404, "RESOURCE_NOT_FOUND")


# --- Activar y desactivar ---------------------------------------------------------------


def test_deactivate_requires_reason(admin_client, partner):
    url = f"{partner_url(partner)}/deactivate"
    assert_error(admin_client.post(url, {}), 400, "VALIDATION_ERROR")

    response = admin_client.post(url, {"reason": "Convenio terminado"})
    assert response.status_code == 200
    assert response.json()["status"] == "INACTIVE"

    response = admin_client.post(f"{partner_url(partner)}/activate")
    assert response.json()["status"] == "ACTIVE"


def test_status_change_emits_signal(admin_client, partner):
    from apps.partners.signals import partner_status_changed

    received = []

    def handler(**kwargs):
        received.append(kwargs)

    partner_status_changed.connect(handler)
    try:
        admin_client.post(f"{partner_url(partner)}/deactivate", {"reason": "Convenio terminado"})
    finally:
        partner_status_changed.disconnect(handler)

    assert len(received) == 1
    assert received[0]["from_status"] == "ACTIVE"
    assert received[0]["to_status"] == "INACTIVE"
    assert received[0]["reason"] == "Convenio terminado"


def test_only_admin_changes_partner_status(advisor_client, partner):
    response = advisor_client.post(f"{partner_url(partner)}/deactivate", {"reason": "x"})
    assert_error(response, 403, "PERMISSION_DENIED")


# --- Membresías -------------------------------------------------------------------------


def members_url(partner: Partner) -> str:
    return f"{partner_url(partner)}/members"


def test_admin_adds_partner_user_as_member(admin_client, partner, make_user):
    user = make_user(email="nuevo@example.com", role_code="CONSTRUCTION_PARTNER")

    response = admin_client.post(
        members_url(partner), {"user_id": str(user.id), "job_title": "Gerente comercial"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "nuevo@example.com"
    assert body["status"] == "ACTIVE"
    assert body["started_at"] == date.today().isoformat()
    assert body["ended_at"] is None


def test_member_must_have_partner_role(admin_client, partner, advisor_user):
    response = admin_client.post(members_url(partner), {"user_id": str(advisor_user.id)})
    assert_error(response, 422, "USER_NOT_ELIGIBLE")


def test_member_must_exist(admin_client, partner):
    response = admin_client.post(members_url(partner), {"user_id": str(uuid.uuid4())})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_user_cannot_belong_to_two_active_partners(admin_client, partner_user, other_partner):
    response = admin_client.post(members_url(other_partner), {"user_id": str(partner_user.id)})
    assert_error(response, 409, "USER_ALREADY_IN_PARTNER")


def test_cannot_add_members_to_inactive_partner(admin_client, partner, make_user):
    partner.status = "INACTIVE"
    partner.save()
    user = make_user(email="nuevo@example.com", role_code="CONSTRUCTION_PARTNER")
    response = admin_client.post(members_url(partner), {"user_id": str(user.id)})
    assert_error(response, 422, "PARTNER_NOT_ACTIVE")


def test_ending_membership_keeps_history_and_frees_the_user(
    admin_client, partner_user, partner, other_partner
):
    membership = PartnerMembership.objects.get(user=partner_user)
    url = f"/api/v1/partner-memberships/{membership.id}"

    assert admin_client.delete(url).status_code == 204
    membership.refresh_from_db()
    assert membership.status == "INACTIVE"
    assert membership.ended_at == date.today()
    assert admin_client.delete(url).status_code == 204  # Idempotente.

    response = admin_client.post(members_url(other_partner), {"user_id": str(partner_user.id)})
    assert response.status_code == 201


def test_ended_membership_cannot_be_reactivated(admin_client, partner_user):
    membership = PartnerMembership.objects.get(user=partner_user)
    url = f"/api/v1/partner-memberships/{membership.id}"
    admin_client.delete(url)

    assert_error(admin_client.patch(url, {"status": "ACTIVE"}), 409, "MEMBERSHIP_ENDED")


def test_update_membership(admin_client, partner_user):
    membership = PartnerMembership.objects.get(user=partner_user)
    url = f"/api/v1/partner-memberships/{membership.id}"

    body = admin_client.patch(url, {"job_title": "Director", "status": "INACTIVE"}).json()
    assert body["job_title"] == "Director"
    assert body["status"] == "INACTIVE"


def test_partner_user_only_sees_own_membership(partner_client, partner, partner_user, make_user):
    colleague = make_user(email="colega@example.com", role_code="CONSTRUCTION_PARTNER")
    colleague_membership = PartnerMembership.objects.create(
        partner=partner, user=colleague, started_at=date(2026, 1, 1)
    )

    body = partner_client.get(members_url(partner)).json()
    assert [item["user"]["email"] for item in body["items"]] == ["constructora@example.com"]
    response = partner_client.get(f"/api/v1/partner-memberships/{colleague_membership.id}")
    assert_error(response, 404, "RESOURCE_NOT_FOUND")


def test_partner_user_cannot_manage_members(partner_client, partner, make_user):
    user = make_user(email="nuevo@example.com", role_code="CONSTRUCTION_PARTNER")
    response = partner_client.post(members_url(partner), {"user_id": str(user.id)})
    assert_error(response, 403, "PERMISSION_DENIED")


def test_me_returns_partner_id_for_partner_users(partner_client, partner):
    body = partner_client.get(ME_URL).json()
    assert body["role"] == "CONSTRUCTION_PARTNER"
    assert body["scope"]["partner_id"] == str(partner.id)


def test_me_partner_id_is_null_after_membership_ends(partner_user, partner):
    PartnerMembership.objects.filter(user=partner_user).update(
        status="INACTIVE", ended_at=date.today()
    )
    body = client_for(partner_user).get(ME_URL).json()
    assert body["scope"]["partner_id"] is None
