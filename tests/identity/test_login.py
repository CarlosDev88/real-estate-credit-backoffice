import pytest
from django.conf import settings

from apps.identity.cookies import access_cookie_name, refresh_cookie_name
from apps.identity.models import AuthSession
from apps.identity.tokens import decode_access_token, hash_token
from tests.helpers import DEFAULT_PASSWORD, LOGIN_URL, ME_URL, assert_error, login

pytestmark = pytest.mark.django_db


def test_login_returns_profile_and_sets_session_cookies(api_client, user):
    response = login(api_client)

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": str(user.id),
        "name": "Andrea García",
        "email": "asesor@example.com",
        "role": "ADVISOR",
    }
    assert body["permissions"] == ["applications.read_assigned", "documents.review"]

    access = response.cookies[access_cookie_name()]
    refresh = response.cookies[refresh_cookie_name()]
    assert access_cookie_name() == "__Host-app_access"
    assert refresh_cookie_name() == "__Host-app_refresh"
    for cookie in (access, refresh):
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Lax"
        assert cookie["path"] == "/"
        assert not cookie["domain"]
    assert int(access["max-age"]) == 15 * 60
    assert int(refresh["max-age"]) == 8 * 60 * 60

    # La cookie CSRF es legible por el frontend.
    csrf = response.cookies[settings.CSRF_COOKIE_NAME]
    assert csrf.value
    assert not csrf["httponly"]


def test_login_stores_only_the_refresh_token_hash(api_client, user):
    response = login(api_client)
    raw_refresh = response.cookies[refresh_cookie_name()].value

    session = AuthSession.objects.get(user=user)
    assert session.refresh_token_hash == hash_token(raw_refresh)
    assert session.refresh_token_hash != raw_refresh
    assert session.revoked_at is None

    claims = decode_access_token(response.cookies[access_cookie_name()].value)
    assert claims.session_id == session.id
    assert claims.user_id == user.id


def test_login_records_ip_user_agent_and_last_login(api_client, user):
    api_client.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD},
        HTTP_USER_AGENT="Mozilla/5.0 Prueba",
        REMOTE_ADDR="203.0.113.10",
    )
    session = AuthSession.objects.get(user=user)
    assert session.ip_address == "203.0.113.10"
    assert session.user_agent_summary == "Mozilla/5.0 Prueba"
    user.refresh_from_db()
    assert user.last_login is not None


def test_login_ignores_untrusted_x_forwarded_for(api_client, user):
    api_client.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD},
        REMOTE_ADDR="203.0.113.10",
        HTTP_X_FORWARDED_FOR="198.51.100.99",
    )
    assert AuthSession.objects.get(user=user).ip_address == "203.0.113.10"


def test_login_email_is_case_insensitive(api_client, user):
    response = login(api_client, email="  ASESOR@Example.COM ")
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_error(api_client, user):
    wrong_password = assert_error(
        login(api_client, password="otra-clave"), 401, "INVALID_CREDENTIALS"
    )
    unknown_email = assert_error(
        login(api_client, email="nadie@example.com"), 401, "INVALID_CREDENTIALS"
    )
    assert wrong_password["message"] == unknown_email["message"]
    assert not AuthSession.objects.exists()


def test_inactive_user_cannot_login(api_client, make_user):
    make_user(is_active=False)
    assert_error(login(api_client), 403, "USER_INACTIVE")
    assert not AuthSession.objects.exists()


def test_inactive_user_with_wrong_password_does_not_reveal_status(api_client, make_user):
    make_user(is_active=False)
    assert_error(login(api_client, password="otra-clave"), 401, "INVALID_CREDENTIALS")


def test_soft_deleted_user_cannot_login(api_client, make_user):
    from django.utils import timezone

    make_user(deleted_at=timezone.now())
    assert_error(login(api_client), 401, "INVALID_CREDENTIALS")


def test_login_rejects_unknown_fields(api_client, user):
    response = api_client.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD, "is_superuser": True},
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"] == [
        {"field": "is_superuser", "code": "UNKNOWN_FIELD", "message": "Campo no permitido."}
    ]


def test_login_validates_required_fields(api_client, db):
    body = assert_error(api_client.post(LOGIN_URL, {}), 400, "VALIDATION_ERROR")
    assert {detail["field"] for detail in body["details"]} == {"email", "password"}


def test_login_rejects_malformed_json(api_client, db):
    response = api_client.post(LOGIN_URL, "{no-json", content_type="application/json")
    assert_error(response, 400, "MALFORMED_REQUEST")


def test_login_is_rate_limited_per_email_and_ip(api_client, user):
    for _ in range(5):
        assert login(api_client, password="otra-clave").status_code == 401

    response = login(api_client)  # Incluso con la contraseña correcta.
    assert_error(response, 429, "RATE_LIMITED")
    assert int(response["Retry-After"]) > 0

    # Otro correo desde la misma IP tiene su propio contador.
    assert login(api_client, email="otro@example.com").status_code == 401


def test_login_works_with_a_stale_access_cookie(api_client, user):
    api_client.cookies[access_cookie_name()] = "token-vencido-o-alterado"
    assert login(api_client).status_code == 200


def test_login_requires_post(api_client, db):
    assert_error(api_client.get(LOGIN_URL), 405, "METHOD_NOT_ALLOWED")


def test_me_returns_profile_permissions_and_scope(logged_client, user):
    response = logged_client.get(ME_URL)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "name": "Andrea García",
        "email": "asesor@example.com",
        "role": "ADVISOR",
        "roles": ["ADVISOR"],
        "permissions": ["applications.read_assigned", "documents.review"],
        "scope": {"assigned_applications_only": True, "partner_id": None},
    }


def test_me_for_admin_is_not_limited_to_assigned_applications(api_client, make_user):
    make_user(email="admin@example.com", role_code="ADMIN")
    login(api_client, email="admin@example.com")

    body = api_client.get(ME_URL).json()
    assert body["role"] == "ADMIN"
    assert body["scope"]["assigned_applications_only"] is False


def test_me_ignores_permissions_of_inactive_roles(api_client, make_user):
    from apps.identity.models import Role

    make_user(permissions=["documents.review"])
    Role.objects.filter(code="ADVISOR").update(is_active=False)
    login(api_client)

    body = api_client.get(ME_URL).json()
    assert body["role"] is None
    assert body["permissions"] == []
