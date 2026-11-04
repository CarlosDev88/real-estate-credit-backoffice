from typing import Any

from django.conf import settings
from rest_framework.test import APIClient

from apps.identity.cookies import access_cookie_name, refresh_cookie_name

DEFAULT_PASSWORD = "Clave-Segura-2026!"

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
PASSWORD_RESET_REQUEST_URL = "/api/v1/auth/password-reset-requests"
PASSWORD_RESET_CONFIRM_URL = "/api/v1/auth/password-resets/confirm"
CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"


def login(
    client: APIClient, email: str = "asesor@example.com", password: str = DEFAULT_PASSWORD
) -> Any:
    return client.post(LOGIN_URL, {"email": email, "password": password})


def access_cookie(client: APIClient) -> str:
    return client.cookies[access_cookie_name()].value


def refresh_cookie(client: APIClient) -> str:
    return client.cookies[refresh_cookie_name()].value


def csrf_token(client: APIClient) -> str:
    return client.cookies[settings.CSRF_COOKIE_NAME].value


def assert_error(response: Any, status_code: int, code: str) -> dict[str, Any]:
    assert response.status_code == status_code, response.content
    body = response.json()
    assert body["code"] == code, body
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["request_id"] == response["X-Request-ID"]
    return body


def role_permissions(role_code: str) -> list[str]:
    """Permisos sembrados de un rol, ordenados como los devuelve la API."""
    from apps.identity.models import Permission

    return sorted(
        Permission.objects.filter(role_assignments__role__code=role_code).values_list(
            "code", flat=True
        )
    )


def cookie_was_cleared(response: Any, name: str) -> bool:
    cookie = response.cookies.get(name)
    return cookie is not None and cookie.value == "" and str(cookie["max-age"]) == "0"
