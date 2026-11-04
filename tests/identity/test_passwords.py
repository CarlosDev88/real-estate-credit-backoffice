import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from apps.identity.models import AuthSession, PasswordResetToken
from apps.identity.tokens import hash_token
from tests.helpers import (
    CHANGE_PASSWORD_URL,
    DEFAULT_PASSWORD,
    ME_URL,
    PASSWORD_RESET_CONFIRM_URL,
    PASSWORD_RESET_REQUEST_URL,
    assert_error,
    csrf_token,
    login,
)

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Otra-Clave-Robusta-2027"


def _request_reset(client, email="asesor@example.com"):
    # El correo se envía en `on_commit`, y en pruebas la transacción nunca confirma.
    with TestCase.captureOnCommitCallbacks(execute=True):
        return client.post(PASSWORD_RESET_REQUEST_URL, {"email": email})


def _token_from_last_email() -> str:
    match = re.search(r"\?token=([A-Za-z0-9_\-]+)", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


# --- Solicitud de recuperación ----------------------------------------------------------


def test_reset_request_sends_email_and_stores_only_the_hash(api_client, user):
    with freeze_time("2026-11-04 10:00:00"):
        response = _request_reset(api_client)

    assert response.status_code == 202
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["asesor@example.com"]
    assert "http://localhost:3000/restablecer-contrasena?token=" in mail.outbox[0].body

    raw_token = _token_from_last_email()
    reset_token = PasswordResetToken.objects.get(user=user)
    assert reset_token.token_hash == hash_token(raw_token)
    assert reset_token.expires_at - reset_token.created_at == timedelta(minutes=30)


def test_reset_request_response_is_uniform_for_unknown_emails(api_client, user):
    known = _request_reset(api_client)
    unknown = _request_reset(api_client, email="nadie@example.com")

    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert len(mail.outbox) == 1
    assert PasswordResetToken.objects.count() == 1


def test_reset_request_ignores_inactive_users(api_client, make_user):
    make_user(is_active=False)
    assert _request_reset(api_client).status_code == 202
    assert mail.outbox == []


def test_new_reset_request_invalidates_the_previous_link(api_client, user):
    _request_reset(api_client)
    first_token = _token_from_last_email()
    _request_reset(api_client)

    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL, {"token": first_token, "new_password": NEW_PASSWORD}
    )
    assert_error(response, 400, "PASSWORD_RESET_TOKEN_INVALID")


def test_reset_request_is_rate_limited(api_client, user):
    for _ in range(3):
        assert _request_reset(api_client).status_code == 202
    assert_error(_request_reset(api_client), 429, "RATE_LIMITED")


# --- Confirmación -----------------------------------------------------------------------


def test_confirm_reset_changes_password_and_revokes_all_sessions(api_client, user):
    login(api_client)
    _request_reset(api_client)

    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL,
        {"token": _token_from_last_email(), "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert not AuthSession.objects.filter(user=user, revoked_at__isnull=True).exists()
    assert_error(api_client.get(ME_URL), 401, "SESSION_EXPIRED")
    assert login(api_client, password=NEW_PASSWORD).status_code == 200


def test_reset_token_is_single_use(api_client, user):
    _request_reset(api_client)
    token = _token_from_last_email()
    payload = {"token": token, "new_password": NEW_PASSWORD}

    assert api_client.post(PASSWORD_RESET_CONFIRM_URL, payload).status_code == 204
    assert_error(
        api_client.post(PASSWORD_RESET_CONFIRM_URL, payload), 400, "PASSWORD_RESET_TOKEN_INVALID"
    )


def test_expired_reset_token_is_rejected(api_client, user):
    with freeze_time("2026-11-04 10:00:00"):
        _request_reset(api_client)
    token = _token_from_last_email()

    with freeze_time("2026-11-04 10:31:00"):
        response = api_client.post(
            PASSWORD_RESET_CONFIRM_URL, {"token": token, "new_password": NEW_PASSWORD}
        )
    assert_error(response, 400, "PASSWORD_RESET_TOKEN_INVALID")


def test_unknown_reset_token_is_rejected(api_client, db):
    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL, {"token": "inventado", "new_password": NEW_PASSWORD}
    )
    assert_error(response, 400, "PASSWORD_RESET_TOKEN_INVALID")


def test_reset_rejects_weak_password_and_keeps_token_usable(api_client, user):
    _request_reset(api_client)
    token = _token_from_last_email()

    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL, {"token": token, "new_password": "12345678"}
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert {detail["field"] for detail in body["details"]} == {"new_password"}

    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL, {"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204


def test_reset_token_of_deactivated_user_is_rejected(api_client, user):
    _request_reset(api_client)
    token = _token_from_last_email()
    user.is_active = False
    user.save()

    response = api_client.post(
        PASSWORD_RESET_CONFIRM_URL, {"token": token, "new_password": NEW_PASSWORD}
    )
    assert_error(response, 400, "PASSWORD_RESET_TOKEN_INVALID")


# --- Cambio de contraseña ---------------------------------------------------------------


def test_change_password_keeps_current_session_and_revokes_others(logged_client, user):
    from rest_framework.test import APIClient

    other_device = APIClient()
    login(other_device)

    response = logged_client.post(
        CHANGE_PASSWORD_URL,
        {"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert logged_client.get(ME_URL).status_code == 200
    assert_error(other_device.get(ME_URL), 401, "SESSION_EXPIRED")


def test_change_password_rejects_wrong_current_password(logged_client, user):
    response = logged_client.post(
        CHANGE_PASSWORD_URL, {"current_password": "incorrecta", "new_password": NEW_PASSWORD}
    )
    assert_error(response, 400, "INVALID_CURRENT_PASSWORD")
    user.refresh_from_db()
    assert user.check_password(DEFAULT_PASSWORD)


def test_change_password_rejects_same_password(logged_client):
    response = logged_client.post(
        CHANGE_PASSWORD_URL,
        {"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_change_password_requires_authentication(api_client, db):
    response = api_client.post(
        CHANGE_PASSWORD_URL, {"current_password": "x", "new_password": NEW_PASSWORD}
    )
    assert_error(response, 401, "NOT_AUTHENTICATED")


def test_change_password_requires_csrf_token(csrf_client, user):
    login(csrf_client)
    payload = {"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD}

    assert_error(csrf_client.post(CHANGE_PASSWORD_URL, payload), 403, "CSRF_FAILED")
    response = csrf_client.post(
        CHANGE_PASSWORD_URL, payload, HTTP_X_CSRFTOKEN=csrf_token(csrf_client)
    )
    assert response.status_code == 204


def test_change_password_is_rate_limited(logged_client):
    payload = {"current_password": "incorrecta", "new_password": NEW_PASSWORD}
    for _ in range(5):
        logged_client.post(CHANGE_PASSWORD_URL, payload)
    assert_error(logged_client.post(CHANGE_PASSWORD_URL, payload), 429, "RATE_LIMITED")


def test_password_is_hashed_with_argon2_in_production_settings():
    from config.settings import base

    assert base.PASSWORD_HASHERS == ["django.contrib.auth.hashers.Argon2PasswordHasher"]


def test_consumed_reset_tokens_keep_their_history(api_client, user):
    _request_reset(api_client)
    api_client.post(
        PASSWORD_RESET_CONFIRM_URL,
        {"token": _token_from_last_email(), "new_password": NEW_PASSWORD},
    )
    reset_token = PasswordResetToken.objects.get(user=user)
    assert reset_token.consumed_at is not None
    assert reset_token.consumed_at <= timezone.now()
