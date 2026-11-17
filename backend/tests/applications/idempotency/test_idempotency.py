"""``Idempotency-Key`` en los ``POST`` críticos (Parte 3 del paso 13, API §6)."""

from collections.abc import Callable
from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.applications.models import ApplicationStatusHistory, CreditApplication
from apps.documents.models import DocumentPackageJob
from apps.filings.models import Filing, FilingResponse
from apps.idempotency import services
from apps.idempotency.decorators import idempotent
from apps.idempotency.models import IdempotencyKey
from apps.identity.models import BuyerAccessLink, BuyerSession, User
from tests.applications.buyer_access.conftest import make_link, make_session
from tests.applications.conftest import application_url
from tests.applications.filings.test_filings_api import filings_url, package, payload, ready
from tests.applications.filings.test_responses_api import (
    REJECTED_BODY,
    filed,
    responses_url,
)
from tests.helpers import assert_error

__all__ = ["filed", "make_link", "make_session", "package", "ready"]

pytestmark = pytest.mark.django_db

KEY = "5f0c6a4e-7a51-4d3e-9a51-1f8a0c7b2d10"


def with_key(key: str = KEY) -> dict[str, str]:
    return {"Idempotency-Key": key}


def transitions_url(application: CreditApplication) -> str:
    return application_url(application, "/status-transitions")


def packages_url(application: CreditApplication) -> str:
    return application_url(application, "/document-package-jobs")


def links_url(application: CreditApplication) -> str:
    return application_url(application, "/buyer-access-links")


def to_review(application: CreditApplication) -> dict[str, Any]:
    """De `DRAFT` a `WAITING_BUYER_DATA`, con la versión vigente."""
    application.refresh_from_db()
    return {"target_status": "WAITING_BUYER_DATA", "expected_version": application.version}


@pytest.fixture
def waiting(application: CreditApplication) -> CreditApplication:
    """Solicitud en `DRAFT`, lista para pasar a esperar los datos del comprador."""
    return application


def changes(application: CreditApplication) -> int:
    return ApplicationStatusHistory.objects.filter(application=application).count()


# --- Comportamiento ---------------------------------------------------------------------


def test_without_the_header_nothing_changes(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    body = to_review(waiting)

    assert advisor_client.post(transitions_url(waiting), body).status_code == 200
    assert_error(advisor_client.post(transitions_url(waiting), body), 409, "STALE_VERSION")
    assert not IdempotencyKey.objects.exists()


def test_a_repeat_returns_the_original_response(
    advisor_client: APIClient, advisor_user: User, waiting: CreditApplication
) -> None:
    body = to_review(waiting)
    first = advisor_client.post(transitions_url(waiting), body, headers=with_key())

    assert first.status_code == 200, first.content
    again = advisor_client.post(transitions_url(waiting), body, headers=with_key())

    assert again.status_code == 200
    assert again.json() == first.json()
    assert again["ETag"] == first["ETag"]
    assert changes(waiting) == 1
    record = IdempotencyKey.objects.get()
    assert (record.user, record.buyer_session) == (advisor_user, None)
    assert (record.method, record.route_fingerprint) == ("POST", transitions_url(waiting))
    assert abs(record.expires_at - record.created_at - timedelta(hours=24)) < timedelta(seconds=1)
    assert record.response_headers == {"ETag": first["ETag"]}


def test_the_body_order_does_not_matter(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    body = to_review(waiting)
    reordered = dict(reversed(list(body.items())))

    assert (
        advisor_client.post(transitions_url(waiting), body, headers=with_key()).status_code == 200
    )
    assert (
        advisor_client.post(transitions_url(waiting), reordered, headers=with_key()).status_code
        == 200
    )
    assert changes(waiting) == 1


def test_another_body_with_the_same_key_is_a_conflict(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    body = to_review(waiting)
    assert (
        advisor_client.post(transitions_url(waiting), body, headers=with_key()).status_code == 200
    )

    response = advisor_client.post(
        transitions_url(waiting), {**body, "comment": "Otro"}, headers=with_key()
    )

    assert_error(response, 422, "IDEMPOTENCY_CONFLICT")


def test_only_successful_responses_are_kept(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    stale = {**to_review(waiting), "expected_version": 99}

    assert_error(
        advisor_client.post(transitions_url(waiting), stale, headers=with_key()),
        409,
        "STALE_VERSION",
    )

    assert not IdempotencyKey.objects.exists()
    # La clave quedó libre: el reintento corregido corre.
    response = advisor_client.post(transitions_url(waiting), to_review(waiting), headers=with_key())
    assert response.status_code == 200, response.content


def test_a_key_in_progress_answers_409(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    body = to_review(waiting)
    assert (
        advisor_client.post(transitions_url(waiting), body, headers=with_key()).status_code == 200
    )
    # Como si la primera petición siguiera corriendo.
    IdempotencyKey.objects.update(response_status=None, response_body=None)

    response = advisor_client.post(transitions_url(waiting), body, headers=with_key())

    assert_error(response, 409, "IDEMPOTENCY_IN_PROGRESS")
    assert changes(waiting) == 1


def test_a_simultaneous_claim_answers_409(
    advisor_client: APIClient,
    advisor_user: User,
    waiting: CreditApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos peticiones a la vez: la segunda no ve la fila de la primera al buscarla y
    choca con la restricción única al insertarla."""
    IdempotencyKey.objects.create(
        user=advisor_user,
        key=KEY,
        method="POST",
        route_fingerprint=transitions_url(waiting),
        request_hash="0" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    monkeypatch.setattr(services, "_keys_of", lambda *args: IdempotencyKey.objects.none())

    response = advisor_client.post(transitions_url(waiting), to_review(waiting), headers=with_key())

    assert_error(response, 409, "IDEMPOTENCY_IN_PROGRESS")


def test_another_actor_has_its_own_keys(
    advisor_client: APIClient,
    admin_client: APIClient,
    ready: CreditApplication,
) -> None:
    first = advisor_client.post(packages_url(ready), headers=with_key())
    second = admin_client.post(packages_url(ready), headers=with_key())

    assert (first.status_code, second.status_code) == (201, 200), second.content
    assert second.json()["id"] == first.json()["id"]
    assert IdempotencyKey.objects.count() == 2


def test_an_expired_key_runs_again(advisor_client: APIClient, ready: CreditApplication) -> None:
    first = advisor_client.post(packages_url(ready), headers=with_key())
    assert first.status_code == 201
    assert advisor_client.post(packages_url(ready), headers=with_key()).status_code == 201
    IdempotencyKey.objects.update(
        created_at=timezone.now() - timedelta(hours=25),
        expires_at=timezone.now() - timedelta(hours=1),
    )

    again = advisor_client.post(packages_url(ready), headers=with_key())

    # Ya no es la respuesta guardada: la vista corrió y encontró el paquete vivo.
    assert again.status_code == 200
    assert IdempotencyKey.objects.get().response_status == 200


@pytest.mark.parametrize("key", ["", "con espacios", "x" * 101, "ñandú"])
def test_a_malformed_key_is_rejected(
    advisor_client: APIClient, waiting: CreditApplication, key: str
) -> None:
    response = advisor_client.post(
        transitions_url(waiting), to_review(waiting), headers=with_key(key)
    )

    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "Idempotency-Key"
    assert changes(waiting) == 0


# --- Las cinco operaciones --------------------------------------------------------------


def test_filing(advisor_client: APIClient, ready: CreditApplication, package: Any) -> None:
    body = payload(ready, package)

    first = advisor_client.post(filings_url(ready), body, format="json", headers=with_key())
    again = advisor_client.post(filings_url(ready), body, format="json", headers=with_key())

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert again["ETag"] == first["ETag"]
    assert Filing.objects.count() == 1
    assert IdempotencyKey.objects.get().resource_id == Filing.objects.get().pk


def test_bank_response(advisor_client: APIClient, filed: Filing) -> None:
    application = CreditApplication.objects.get(pk=filed.application_id)
    body = {
        "response_type": "REJECTED",
        "received_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
        "expected_version": application.version,
        **REJECTED_BODY,
    }

    first = advisor_client.post(responses_url(filed), body, format="json", headers=with_key())
    again = advisor_client.post(responses_url(filed), body, format="json", headers=with_key())

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert FilingResponse.objects.count() == 1


def test_package(advisor_client: APIClient, ready: CreditApplication) -> None:
    first = advisor_client.post(packages_url(ready), headers=with_key())
    again = advisor_client.post(packages_url(ready), headers=with_key())

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert DocumentPackageJob.objects.count() == 1


def test_status_transition_declares_its_etag(
    advisor_client: APIClient, waiting: CreditApplication
) -> None:
    body = to_review(waiting)
    first = advisor_client.post(transitions_url(waiting), body, headers=with_key())

    assert (
        first["ETag"]
        == advisor_client.post(transitions_url(waiting), body, headers=with_key())["ETag"]
    )


def test_magic_link_is_not_replayed(
    advisor_client: APIClient, application: CreditApplication
) -> None:
    first = advisor_client.post(links_url(application), {}, format="json", headers=with_key())

    assert first.status_code == 201, first.content
    assert first.json()["url"]
    again = advisor_client.post(links_url(application), {}, format="json", headers=with_key())

    assert_error(again, 409, "IDEMPOTENCY_REPLAY_UNAVAILABLE")
    assert BuyerAccessLink.objects.count() == 1
    record = IdempotencyKey.objects.get()
    assert (record.response_status, record.response_body) == (201, None)
    assert record.resource_id == BuyerAccessLink.objects.get().pk
    assert record.response_headers == {}


def test_the_contract_declares_the_header_in_the_five_operations() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    expected = {
        "applications_filings_create",
        "filings_responses_create",
        "applications_status_transitions_create",
        "applications_document_package_jobs_create",
        "buyer_access_links_create",
    }
    declared = set()
    for item in schema["paths"].values():
        for operation in item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            headers = [
                parameter
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "header" and parameter["name"] == "Idempotency-Key"
            ]
            if headers:
                assert headers[0].get("required", False) is False
                assert "IDEMPOTENCY_CONFLICT" in operation["responses"]["422"]["description"]
                assert "IDEMPOTENCY_IN_PROGRESS" in operation["responses"]["409"]["description"]
                declared.add(operation["operationId"])
    assert declared == expected


# --- El decorador -----------------------------------------------------------------------


class _EchoView(APIView):
    """Vista mínima: responde el código que pida el cuerpo."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @idempotent()
    def post(self, request: Request) -> Response:
        return Response(request.data.get("answer"), status=request.data["status"])


def _call(actor: Any, body: dict[str, Any], *, session: BuyerSession | None = None) -> Response:
    request = APIRequestFactory().post("/api/v1/eco", body, format="json", headers=with_key())
    force_authenticate(request, user=actor, token=session)  # type: ignore[arg-type]
    response: Response = _EchoView.as_view()(request)
    return response


def test_a_buyer_session_is_an_actor(make_session: Callable[..., BuyerSession]) -> None:
    from django.contrib.auth.models import AnonymousUser

    session = make_session()

    first = _call(AnonymousUser(), {"status": 201, "answer": ["sin id"]}, session=session)
    again = _call(AnonymousUser(), {"status": 201, "answer": ["sin id"]}, session=session)

    assert (first.status_code, again.status_code) == (201, 201)
    record = IdempotencyKey.objects.get()
    assert (record.user, record.buyer_session, record.resource_id) == (None, session, None)


def test_a_non_2xx_response_releases_the_key(advisor_user: User) -> None:
    assert _call(advisor_user, {"status": 400, "answer": {"id": "no-es-uuid"}}).status_code == 400
    assert not IdempotencyKey.objects.exists()

    response = _call(advisor_user, {"status": 200, "answer": {"id": "no-es-uuid"}})

    assert response.status_code == 200
    assert IdempotencyKey.objects.get().resource_id is None


def test_an_anonymous_request_skips_the_key() -> None:
    request = APIRequestFactory().post("/api/v1/eco", {"status": 200}, format="json")
    request.META["HTTP_IDEMPOTENCY_KEY"] = KEY
    view = _EchoView.as_view()

    assert view(request).status_code == 200
    assert not IdempotencyKey.objects.exists()


def test_the_actor_is_required_by_the_schema(advisor_user: User) -> None:
    with pytest.raises(IntegrityError):
        IdempotencyKey.objects.create(
            key=KEY,
            method="POST",
            route_fingerprint="/x",
            request_hash="0" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )


# --- Limpieza ---------------------------------------------------------------------------


def test_purge_deletes_only_the_expired_keys(advisor_user: User) -> None:
    now = timezone.now()
    for index, expires_at in enumerate((now - timedelta(minutes=1), now + timedelta(hours=1))):
        record = IdempotencyKey.objects.create(
            user=advisor_user,
            key=f"k-{index}",
            method="POST",
            route_fingerprint="/x",
            request_hash="0" * 64,
            expires_at=now + timedelta(hours=1),
        )
        IdempotencyKey.objects.filter(pk=record.pk).update(
            created_at=expires_at - timedelta(hours=24), expires_at=expires_at
        )
    out = StringIO()

    call_command("purge_idempotency_keys", stdout=out)

    assert "Claves de idempotencia borradas: 1." in out.getvalue()
    assert list(IdempotencyKey.objects.values_list("key", flat=True)) == ["k-1"]
