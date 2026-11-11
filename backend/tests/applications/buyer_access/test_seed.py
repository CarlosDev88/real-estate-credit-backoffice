"""Semilla y configuración del acceso del comprador: permisos, canal y consentimientos."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.catalogs.models import Catalog
from apps.identity.models import ConsentDefinition, consent_content_hash
from tests.helpers import role_permissions

pytestmark = pytest.mark.django_db

BUYER_ACCESS_PERMISSIONS = {"buyer_access.create", "buyer_access.read", "buyer_access.revoke"}


def seeded(role_code: str) -> set[str]:
    return {
        code
        for code in role_permissions(role_code)
        if code.startswith(("buyer_access.", "consents."))
    }


@pytest.mark.parametrize("role_code", ["ADMIN", "ADVISOR"])
def test_admin_and_advisor_issue_links_and_read_consents(role_code: str) -> None:
    assert seeded(role_code) == BUYER_ACCESS_PERMISSIONS | {"consents.read"}


def test_broker_issues_links_but_does_not_read_consents() -> None:
    assert seeded("INDEPENDENT_BROKER") == BUYER_ACCESS_PERMISSIONS


def test_construction_partner_has_no_buyer_access() -> None:
    assert seeded("CONSTRUCTION_PARTNER") == set()


def test_delivery_channels_are_managed_by_the_backend() -> None:
    catalog = Catalog.objects.get(code="buyer_access_channel")

    assert not catalog.is_public
    assert not catalog.is_manageable
    assert list(catalog.items.order_by("sort_order").values_list("code", flat=True)) == [
        "COPY_LINK",
        "EMAIL",
    ]


def test_both_consents_are_seeded_as_effective_provisional_versions() -> None:
    definitions = {definition.code: definition for definition in ConsentDefinition.objects.all()}

    assert set(definitions) == {"DATA_PROCESSING", "CO_APPLICANT_AUTHORIZATION"}
    for definition in definitions.values():
        assert definition.version == 1
        assert definition.retired_at is None
        assert definition.effective_from <= timezone.now()
        assert definition.body.startswith("TEXTO PROVISIONAL")
        assert definition.content_hash == consent_content_hash(definition.body)


def test_buyer_access_settings_defaults() -> None:
    assert settings.BUYER_ACCESS_LINK_DEFAULT_HOURS == 72
    assert settings.BUYER_ACCESS_LINK_MAX_HOURS == 168
    assert timedelta(hours=24) == settings.BUYER_SESSION_LIFETIME
    assert settings.AUTH_RATE_LIMITS["buyer_access_consume"] == "5/1h"
    assert settings.AUTH_RATE_LIMITS["buyer_access_issue"] == "3/1h"
