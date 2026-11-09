"""Fixtures del acceso del comprador (paso 9).

Viven bajo ``tests/applications`` para reutilizar sus fixtures de solicitud, titular y
usuarios internos.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.identity.models import (
    BuyerAccessLink,
    BuyerSession,
    ConsentAction,
    ConsentDefinition,
    ConsentRecord,
)
from apps.identity.tokens import generate_opaque_token, hash_token

CONSUME_URL = "/api/v1/buyer-access/consume"

LinkFactory = Callable[..., BuyerAccessLink]


def pending_token(make_link: LinkFactory, **extra: Any) -> str:
    """Crea un enlace pendiente y devuelve su token en claro."""
    token = generate_opaque_token()
    make_link(token_hash=hash_token(token), **extra)
    return token


def consume(client: APIClient, token: str, **extra: Any) -> Any:
    return client.post(CONSUME_URL, {"token": token}, **extra)


def if_match(application: CreditApplication) -> dict[str, str]:
    """Cabecera con la versión vigente, para `headers=`."""
    application.refresh_from_db()
    return {"If-Match": f'"{application.version}"'}


def version_of(application: CreditApplication) -> int:
    application.refresh_from_db()
    return application.version


def set_status(application: CreditApplication, status: str) -> None:
    CreditApplication.objects.filter(pk=application.pk).update(status=status)


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


@pytest.fixture
def buyer_client(make_link: LinkFactory) -> APIClient:
    """Navegador del comprador con la sesión ya abierta."""
    client = APIClient()
    assert consume(client, pending_token(make_link)).status_code == 200
    return client


@pytest.fixture
def buyer_csrf_client(make_link: LinkFactory) -> APIClient:
    """Igual que ``buyer_client``, pero sujeto a la validación CSRF."""
    client = APIClient(enforce_csrf_checks=True)
    assert consume(client, pending_token(make_link)).status_code == 200
    return client


@pytest.fixture
def accept_consents(application: CreditApplication) -> Callable[[], None]:
    """Acepta los dos consentimientos para el titular, como si lo hubiera hecho el portal."""

    def _accept() -> None:
        for definition in ConsentDefinition.objects.filter(version=1):
            ConsentRecord.objects.create(
                consent_definition=definition,
                client=application.opportunity.client,
                application=application,
                action=ConsentAction.ACCEPTED,
            )

    return _accept


@pytest.fixture
def portal(buyer_client: APIClient, accept_consents: Callable[[], None]) -> APIClient:
    """Comprador con sesión y consentimientos aceptados."""
    accept_consents()
    return buyer_client
