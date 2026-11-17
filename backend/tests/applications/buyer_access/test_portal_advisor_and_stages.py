"""``advisor`` y ``stages`` en ``GET /buyer/applications/{id}``."""

import pytest
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.applications.stages import BUYER_STAGES, progress_stages
from apps.catalogs.workflow import ApplicationStatus
from apps.identity.models import User
from tests.applications.buyer_access.conftest import set_status

pytestmark = pytest.mark.django_db


def detail_url(application: CreditApplication) -> str:
    return f"/api/v1/buyer/applications/{application.pk}"


def test_the_advisor_comes_with_name_email_and_phone(
    portal: APIClient, application: CreditApplication, advisor_user: User
) -> None:
    advisor_user.phone = "+573005550101"
    advisor_user.save(update_fields=["phone"])

    body = portal.get(detail_url(application)).json()

    # Solo esos tres campos: ni id, ni roles, ni otros datos del usuario.
    assert body["advisor"] == {
        "full_name": "Andrea García",
        "email": "asesor@example.com",
        "phone": "+573005550101",
    }


def test_an_advisor_without_phone_has_phone_null(
    portal: APIClient, application: CreditApplication
) -> None:
    body = portal.get(detail_url(application)).json()

    assert body["advisor"]["phone"] is None


def test_an_inactive_advisor_is_not_shown(
    portal: APIClient, application: CreditApplication, advisor_user: User
) -> None:
    User.objects.filter(pk=advisor_user.pk).update(is_active=False)

    assert portal.get(detail_url(application)).json()["advisor"] is None


def test_stages_follow_the_application_status(
    portal: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.FILED)

    body = portal.get(detail_url(application)).json()

    assert body["stages"] == progress_stages(BUYER_STAGES, ApplicationStatus.FILED)
    assert [stage["state"] for stage in body["stages"]] == ["done", "done", "current", "pending"]


def test_a_closed_application_hides_the_stages(
    portal: APIClient, application: CreditApplication
) -> None:
    set_status(application, ApplicationStatus.WITHDRAWN)

    assert portal.get(detail_url(application)).json()["stages"] == []


def test_the_internal_session_cannot_read_the_buyer_detail(
    admin_client: APIClient, application: CreditApplication
) -> None:
    assert admin_client.get(detail_url(application)).status_code == 401
