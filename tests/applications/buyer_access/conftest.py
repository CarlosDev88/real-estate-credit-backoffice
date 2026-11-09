"""Fixtures del acceso del comprador (paso 9).

Viven bajo ``tests/applications`` para reutilizar sus fixtures de solicitud, titular y
usuarios internos.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.identity.models import BuyerAccessLink, BuyerSession
from apps.identity.tokens import generate_opaque_token, hash_token


@pytest.fixture
def make_link(application: CreditApplication) -> Callable[..., BuyerAccessLink]:
    """Enlace creado directamente en la base, para el titular de ``application``."""

    def _make_link(**extra: Any) -> BuyerAccessLink:
        extra.setdefault("application", application)
        extra.setdefault("client", extra["application"].opportunity.client)
        extra.setdefault("token_hash", hash_token(generate_opaque_token()))
        extra.setdefault("expires_at", timezone.now() + timedelta(hours=72))
        return BuyerAccessLink.objects.create(**extra)

    return _make_link


@pytest.fixture
def make_session(make_link: Callable[..., BuyerAccessLink]) -> Callable[..., BuyerSession]:
    """Sesión creada directamente en la base, a partir de un enlace consumido."""

    def _make_session(**extra: Any) -> BuyerSession:
        link = extra.pop("access_link", None) or make_link(consumed_at=timezone.now())
        extra.setdefault("client", link.client)
        extra.setdefault("application", link.application)
        extra.setdefault("session_token_hash", hash_token(generate_opaque_token()))
        extra.setdefault("expires_at", timezone.now() + timedelta(hours=24))
        return BuyerSession.objects.create(access_link=link, **extra)

    return _make_session
