"""Lógica de negocio (OWASP API6:2023), lo determinista (``specs/TAREA-seguridad.md``,
Parte 4.7). Las carreras (10 hilos) necesitan transacciones reales y viven en
``backend/security/race_checks.py``.
"""

import json
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.commissions.models import CommissionSettlement, SettlementStatus
from tests.security.conftest import ADMIN, ADVISOR_OWNER, BUYER_OWNER, World
from tests.security.requests import CONTRACT, client_for

pytestmark = pytest.mark.django_db

API = "/api/v1"
FINANCING_OP = "PUT /api/v1/applications/{application_id}/financing"
PROPERTY_OP = "PUT /api/v1/applications/{application_id}/property"
BUYER_FINANCING_OP = "PUT /api/v1/buyer/applications/{application_id}/financing"
BUYER_PROPERTY_OP = "PUT /api/v1/buyer/applications/{application_id}/property"


def _version(application: CreditApplication) -> int:
    return CreditApplication.objects.only("version").get(pk=application.pk).version


def _request_fields(operation: str) -> set[str]:
    method, path = operation.split(" ", 1)
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    body = spec["paths"][path][method.lower()]["requestBody"]["content"]["application/json"]
    name = body["schema"]["$ref"].rsplit("/", 1)[-1]
    return set(spec["components"]["schemas"][name]["properties"])


def _as_input(current: dict[str, Any], operation: str, **changes: Any) -> dict[str, Any]:
    """El GET actual como cuerpo de escritura válido (``x: {code}`` → ``x_code``,
    ``x: {id}`` → ``x_id``), solo con los campos de entrada del contrato."""
    allowed = _request_fields(operation)
    body: dict[str, Any] = {}
    for key, value in current.items():
        if isinstance(value, dict):
            for suffix in ("code", "id"):
                if f"{key}_{suffix}" in allowed and suffix in value:
                    body[f"{key}_{suffix}"] = value[suffix]
        elif key in allowed:
            body[key] = value
    body.update(changes)
    return body


def _code(response: Any) -> str | None:
    try:
        return response.json().get("code")
    except ValueError:
        return None


@pytest.mark.parametrize("target", ["APPROVED", "FILED", "DISBURSED", "READY_TO_FILE"])
def test_status_cannot_jump_from_draft(world: World, target: str) -> None:
    draft = world.a.draft
    response = client_for(world, ADVISOR_OWNER).post(
        f"{API}/applications/{draft.pk}/status-transitions",
        {"target_status": target, "expected_version": _version(draft)},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert _code(response) == "INVALID_STATE_TRANSITION"
    assert CreditApplication.objects.get(pk=draft.pk).status == "DRAFT"


@pytest.mark.parametrize("stale", [False, True], ids=["if-match-vigente", "if-match-viejo"])
def test_filed_application_cannot_be_edited(world: World, stale: bool) -> None:
    application = world.a.application  # APPROVED: después de radicar.
    version = _version(application) - (1 if stale else 0)
    client = client_for(world, ADVISOR_OWNER)
    url = f"{API}/applications/{application.pk}"
    responses = [
        client.patch(
            url, {"purpose_code": "PURCHASE_USED"}, format="json", HTTP_IF_MATCH=f'"{version}"'
        ),
        client.put(
            f"{url}/financing",
            _as_input(
                client.get(f"{url}/financing").json(), FINANCING_OP, requested_amount_cop=1_000_000
            ),
            format="json",
            HTTP_IF_MATCH=f'"{version}"',
        ),
        client.put(
            f"{url}/property",
            _as_input(
                client.get(f"{url}/property").json(), PROPERTY_OP, estimated_value_cop=1_000_000
            ),
            format="json",
            HTTP_IF_MATCH=f'"{version}"',
        ),
    ]
    for response in responses:
        assert response.status_code in (409, 412), response.content
    assert CreditApplication.objects.get(pk=application.pk).purpose_item.code == "PURCHASE_NEW"


def test_buyer_cannot_change_bank_or_financing_after_filing(world: World) -> None:
    application = world.a.application
    client = client_for(world, BUYER_OWNER)
    version = f'"{_version(application)}"'
    url = f"{API}/buyer/applications/{application.pk}"
    responses = {
        "financing": client.put(
            f"{url}/financing",
            _as_input(
                client.get(f"{url}/financing").json(),
                BUYER_FINANCING_OP,
                requested_amount_cop=1_000_000,
            ),
            format="json",
            HTTP_IF_MATCH=version,
        ),
        "property": client.put(
            f"{url}/property",
            _as_input(
                client.get(f"{url}/property").json(),
                BUYER_PROPERTY_OP,
                estimated_value_cop=1_000_000,
            ),
            format="json",
            HTTP_IF_MATCH=version,
        ),
    }
    for name, response in responses.items():
        assert response.status_code == 409, (name, response.content)


def test_settlement_is_not_duplicated(world: World) -> None:
    """API §23.6: liquidar a mano es idempotente (200 con la vigente si ya existe)."""
    response = client_for(world, ADMIN).post(
        f"{API}/applications/{world.a.disbursed.pk}/commission-settlement"
    )
    assert response.status_code == 200, response.content
    assert response.json()["id"] == str(world.a.settlement.pk)
    active = CommissionSettlement.objects.filter(
        application=world.a.disbursed, status=SettlementStatus.ACTIVE
    )
    assert active.count() == 1


def test_share_cannot_be_paid_twice_and_paid_settlement_cannot_be_voided(world: World) -> None:
    client = client_for(world, ADMIN)
    share, settlement = world.a.share, world.a.settlement
    body = {"paid_at": timezone.localdate().isoformat(), "payment_reference": "TRX-1"}
    first = client.post(f"{API}/commission-shares/{share.pk}/pay", body, format="json")
    second = client.post(f"{API}/commission-shares/{share.pk}/pay", body, format="json")
    void = client.post(
        f"{API}/commission-settlements/{settlement.pk}/void", {"reason": "Prueba"}, format="json"
    )
    assert first.status_code == 200, first.content
    assert second.status_code == 409, second.content
    assert void.status_code == 409, void.content
    assert _code(void) == "COMMISSION_SETTLEMENT_HAS_PAYMENTS"


def test_stale_if_match_is_rejected_on_a_draft(world: World) -> None:
    draft = world.a.draft
    client = client_for(world, ADVISOR_OWNER)
    url = f"{API}/applications/{draft.pk}"
    current = _version(draft)
    ok = client.patch(
        url, {"purpose_code": "PURCHASE_USED"}, format="json", HTTP_IF_MATCH=f'"{current}"'
    )
    stale = client.patch(
        url, {"purpose_code": "PURCHASE_NEW"}, format="json", HTTP_IF_MATCH=f'"{current}"'
    )
    assert ok.status_code == 200, ok.content
    assert stale.status_code in (409, 412), stale.content
    assert CreditApplication.objects.get(pk=draft.pk).purpose_item.code == "PURCHASE_USED"
