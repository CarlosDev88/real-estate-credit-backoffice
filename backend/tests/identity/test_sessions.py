from datetime import datetime, timedelta
from typing import Any

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.identity.cookies import access_cookie_name, refresh_cookie_name
from apps.identity.models import AuthSession, User
from apps.identity.tokens import hash_token
from tests.helpers import (
    LOGOUT_URL,
    ME_URL,
    REFRESH_URL,
    access_cookie,
    assert_error,
    cookie_was_cleared,
    csrf_token,
    login,
    refresh_cookie,
)

pytestmark = pytest.mark.django_db


# --- Access token -----------------------------------------------------------------------


def test_me_without_session_returns_401(api_client: APIClient, db: Any) -> None:
    response = api_client.get(ME_URL)
    assert_error(response, 401, "NOT_AUTHENTICATED")
    assert response["WWW-Authenticate"]


def test_tampered_access_token_is_rejected(logged_client: APIClient) -> None:
    token = access_cookie(logged_client)
    header, payload, signature = token.split(".")
    logged_client.cookies[access_cookie_name()] = f"{header}.{payload}.{signature[::-1]}"

    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_access_token_signed_with_another_key_is_rejected(logged_client: APIClient) -> None:
    claims = jwt.decode(access_cookie(logged_client), options={"verify_signature": False})
    forged = jwt.encode(claims, "otra-clave-de-firma-con-longitud-suficiente", algorithm="HS256")
    logged_client.cookies[access_cookie_name()] = forged

    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_unsigned_access_token_is_rejected(logged_client: APIClient) -> None:
    claims = jwt.decode(access_cookie(logged_client), options={"verify_signature": False})
    logged_client.cookies[access_cookie_name()] = jwt.encode(claims, None, algorithm="none")

    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_access_token_with_wrong_audience_is_rejected(logged_client: APIClient) -> None:
    claims = jwt.decode(access_cookie(logged_client), options={"verify_signature": False})
    claims["aud"] = "otra-aplicacion"
    logged_client.cookies[access_cookie_name()] = jwt.encode(
        claims, settings.AUTH_JWT_SIGNING_KEY, algorithm="HS256"
    )

    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_access_token_expires_after_15_minutes(api_client: APIClient, user: User) -> None:
    with freeze_time("2026-11-04 10:00:00"):
        login(api_client)
    with freeze_time("2026-11-04 10:14:00"):
        assert api_client.get(ME_URL).status_code == 200
    with freeze_time("2026-11-04 10:15:10"):
        assert_error(api_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_revoked_session_cuts_access_immediately(logged_client: APIClient) -> None:
    AuthSession.objects.update(revoked_at=timezone.now())
    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_deactivated_user_loses_access_immediately(logged_client: APIClient, user: User) -> None:
    user.is_active = False
    user.save()
    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


# --- Refresh ----------------------------------------------------------------------------


def test_refresh_rotates_the_session(logged_client: APIClient, user: User) -> None:
    old_refresh = refresh_cookie(logged_client)
    old_access = access_cookie(logged_client)
    old_session = AuthSession.objects.get(user=user)

    response = logged_client.post(REFRESH_URL)

    assert response.status_code == 200
    new_refresh = refresh_cookie(logged_client)
    assert new_refresh != old_refresh
    assert access_cookie(logged_client) != old_access

    old_session.refresh_from_db()
    assert old_session.revoked_at is not None
    new_session = AuthSession.objects.get(refresh_token_hash=hash_token(new_refresh))
    assert new_session.rotated_from_id == old_session.id
    assert new_session.revoked_at is None
    # Refrescar no extiende la sesión más allá del vencimiento original.
    assert new_session.expires_at == old_session.expires_at
    assert datetime.fromisoformat(response.json()["session_expires_at"]) == old_session.expires_at

    assert logged_client.get(ME_URL).status_code == 200


def test_access_token_of_rotated_session_stops_working(logged_client: APIClient) -> None:
    old_access = access_cookie(logged_client)
    logged_client.post(REFRESH_URL)

    logged_client.cookies[access_cookie_name()] = old_access
    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_refresh_works_after_access_token_expired(api_client: APIClient, user: User) -> None:
    with freeze_time("2026-11-04 10:00:00"):
        login(api_client)
    with freeze_time("2026-11-04 10:30:00"):
        assert api_client.post(REFRESH_URL).status_code == 200
        assert api_client.get(ME_URL).status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_the_whole_chain(
    logged_client: APIClient, user: User
) -> None:
    stolen_refresh = refresh_cookie(logged_client)
    logged_client.post(REFRESH_URL)  # El usuario legítimo rota primero.
    logged_client.post(REFRESH_URL)  # Y vuelve a rotar.
    legit_refresh = refresh_cookie(logged_client)

    logged_client.cookies[refresh_cookie_name()] = stolen_refresh
    assert_error(logged_client.post(REFRESH_URL), 401, "SESSION_EXPIRED")

    assert not AuthSession.objects.filter(user=user, revoked_at__isnull=True).exists()
    logged_client.cookies[refresh_cookie_name()] = legit_refresh
    assert_error(logged_client.post(REFRESH_URL), 401, "SESSION_EXPIRED")


def test_reuse_detection_does_not_touch_other_devices(api_client: APIClient, user: User) -> None:
    from rest_framework.test import APIClient

    other_device = APIClient()
    login(other_device)

    login(api_client)
    stolen_refresh = refresh_cookie(api_client)
    api_client.post(REFRESH_URL)
    api_client.cookies[refresh_cookie_name()] = stolen_refresh
    api_client.post(REFRESH_URL)

    assert other_device.get(ME_URL).status_code == 200


def test_refresh_fails_after_absolute_expiry_and_clears_cookies(
    api_client: APIClient, user: User
) -> None:
    with freeze_time("2026-11-04 08:00:00"):
        login(api_client)
    with freeze_time("2026-11-04 16:00:01"):
        response = api_client.post(REFRESH_URL)

    assert_error(response, 401, "SESSION_EXPIRED")
    assert cookie_was_cleared(response, access_cookie_name())
    assert cookie_was_cleared(response, refresh_cookie_name())


def test_refresh_without_cookie_returns_401(api_client: APIClient, db: Any) -> None:
    assert_error(api_client.post(REFRESH_URL), 401, "SESSION_EXPIRED")


def test_refresh_with_unknown_token_returns_401(api_client: APIClient, db: Any) -> None:
    api_client.cookies[refresh_cookie_name()] = "token-inventado"
    assert_error(api_client.post(REFRESH_URL), 401, "SESSION_EXPIRED")


def test_refresh_fails_for_deactivated_user(logged_client: APIClient, user: User) -> None:
    user.is_active = False
    user.save()
    assert_error(logged_client.post(REFRESH_URL), 401, "SESSION_EXPIRED")


def test_access_cookie_never_outlives_the_session(api_client: APIClient, user: User) -> None:
    with freeze_time("2026-11-04 08:00:00"):
        login(api_client)
    with freeze_time("2026-11-04 15:55:00"):
        response = api_client.post(REFRESH_URL)
    assert int(response.cookies[access_cookie_name()]["max-age"]) == 5 * 60


# --- Logout -----------------------------------------------------------------------------


def test_logout_revokes_session_and_clears_cookies(logged_client: APIClient, user: User) -> None:
    response = logged_client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert cookie_was_cleared(response, access_cookie_name())
    assert cookie_was_cleared(response, refresh_cookie_name())
    assert AuthSession.objects.get(user=user).revoked_at is not None


def test_access_token_stops_working_after_logout(logged_client: APIClient) -> None:
    access = access_cookie(logged_client)
    logged_client.post(LOGOUT_URL)

    logged_client.cookies[access_cookie_name()] = access
    assert_error(logged_client.get(ME_URL), 401, "SESSION_EXPIRED")


def test_logout_is_idempotent(api_client: APIClient, db: Any) -> None:
    assert api_client.post(LOGOUT_URL).status_code == 204


def test_logout_only_revokes_the_current_session(api_client: APIClient, user: User) -> None:
    from rest_framework.test import APIClient

    other_device = APIClient()
    login(other_device)
    login(api_client)

    api_client.post(LOGOUT_URL)
    assert other_device.get(ME_URL).status_code == 200


# --- CSRF -------------------------------------------------------------------------------


def test_logout_requires_csrf_token(csrf_client: APIClient, user: User) -> None:
    login(csrf_client)

    assert_error(csrf_client.post(LOGOUT_URL), 403, "CSRF_FAILED")

    response = csrf_client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=csrf_token(csrf_client))
    assert response.status_code == 204


def test_refresh_requires_csrf_token(csrf_client: APIClient, user: User) -> None:
    login(csrf_client)

    assert_error(csrf_client.post(REFRESH_URL), 403, "CSRF_FAILED")

    response = csrf_client.post(REFRESH_URL, HTTP_X_CSRFTOKEN=csrf_token(csrf_client))
    assert response.status_code == 200


def test_safe_methods_do_not_require_csrf(csrf_client: APIClient, user: User) -> None:
    login(csrf_client)
    assert csrf_client.get(ME_URL).status_code == 200


def test_login_rotates_the_csrf_token(csrf_client: APIClient, user: User) -> None:
    csrf_client.get(ME_URL)  # Sin sesión todavía.
    first = login(csrf_client).cookies[settings.CSRF_COOKIE_NAME].value
    second = login(csrf_client).cookies[settings.CSRF_COOKIE_NAME].value
    assert first != second


def test_session_lifetime_matches_configuration(api_client: APIClient, user: User) -> None:
    with freeze_time("2026-11-04 08:00:00"):
        login(api_client)
        session = AuthSession.objects.get(user=user)
        assert session.expires_at - session.created_at == timedelta(hours=8)
