"""Casos de acceso que la matriz no cubre sola (``specs/TAREA-seguridad.md``, Parte 3.4).

- Ids del lado B en el **cuerpo**: la API los trata igual que un id que no existe (mismo
  estado, mismo código) y nunca responde 2xx.
- El comprador A pidiendo recursos del comprador B por la ruta.
- Filtros de listados con ids de otro alcance: 403 o sin datos ajenos, según lo documentado.
- El broker en el detalle de su propia solicitud: solo el resumen.
- La constructora en las rutas de expedientes: 403/404.
- Un usuario desactivado o sin rol, con la cookie de acceso todavía vigente.
"""

import json
import uuid
from typing import Any

import pytest
from django.utils import timezone

from apps.applications.demo_data import _item
from apps.applications.models import CreditApplication
from apps.documents.models import ApplicationDocumentSlot
from apps.filings.services import create_filing
from apps.identity.models import UserRole
from apps.notifications.models import Notification
from tests.security import access_matrix as m
from tests.security.conftest import (
    ADVISOR_OWNER,
    BROKER_OWNER,
    BUYER_OWNER,
    PARTNER,
    World,
)
from tests.security.requests import client_for, contract_operations, send, url_for

pytestmark = pytest.mark.django_db

API = "/api/v1"


def _code(response: Any) -> str | None:
    try:
        return response.json().get("code")
    except (ValueError, AttributeError):
        return None


def _fields(response: Any) -> set[str]:
    try:
        return {detail.get("field") or "" for detail in response.json().get("details", [])}
    except (ValueError, AttributeError):
        return set()


def _mentions(response: Any, *values: Any) -> list[str]:
    text = response.content.decode("utf-8", "replace")
    return [str(value) for value in values if str(value) in text]


def _b_ids(world: World) -> list[Any]:
    b = world.b
    return [
        b.application.pk,
        b.application.code,
        b.draft.pk,
        b.disbursed.pk,
        b.client.pk,
        b.opportunity.pk,
        b.task.pk,
        b.participant.pk,
        b.slot.pk,
        b.file.pk,
    ]


# --- 1. Ids del lado B en el cuerpo ----------------------------------------------------


BodyCase = tuple[str, str, str, dict[str, Any], str]


def _body_cases(world: World) -> tuple[list[BodyCase], dict[str, Any]]:
    """(actor, operación, url, cuerpo con `{ID}`, campo): el id del cuerpo es del lado B."""
    a, b = world.a, world.b
    now = timezone.now().isoformat()
    return [
        (
            ADVISOR_OWNER,
            "POST /api/v1/applications",
            f"{API}/applications",
            {"opportunity_id": "{ID}", "purpose_code": "PURCHASE_NEW"},
            "opportunity_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/applications/{application_id}/participants",
            f"{API}/applications/{a.draft.pk}/participants",
            {"role_code": "CO_APPLICANT", "client_id": "{ID}"},
            "client_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/opportunities",
            f"{API}/opportunities",
            {"client_id": "{ID}", "origin_type": "DIRECT"},
            "client_id",
        ),
        (
            BROKER_OWNER,
            "POST /api/v1/opportunities",
            f"{API}/opportunities",
            {"client_id": "{ID}", "origin_type": "BROKER"},
            "client_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/tasks",
            f"{API}/tasks",
            {"title": "Llamar al comprador", "application_id": "{ID}"},
            "application_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/tasks",
            f"{API}/tasks",
            {"title": "Llamar al comprador", "opportunity_id": "{ID}"},
            "opportunity_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/applications/{application_id}/filings",
            f"{API}/applications/{a.ready.pk}/filings",
            {
                "bank_product_id": str(a.ready.bank_product_id),
                "package_job_id": "{ID}",
                "channel_code": "BANK_PORTAL",
                "filed_at": now,
                "expected_version": a.ready.version,
            },
            "package_job_id",
        ),
        (
            ADVISOR_OWNER,
            "POST /api/v1/filings/{filing_id}/responses",
            f"{API}/filings/{a.filing.pk}/responses",
            {
                "response_type": "OTHER",
                "received_at": now,
                "internal_comment": "Llamada del banco.",
                "corrects_response_id": "{ID}",
                "expected_version": a.application.version,
            },
            "corrects_response_id",
        ),
        (
            ADVISOR_OWNER,
            "PATCH /api/v1/document-slots/{slot_id}/review",
            f"{API}/document-slots/{_ready_slot(a).pk}/review",
            {"decision": "APPROVED", "document_file_id": "{ID}"},
            "document_file_id",
        ),
    ], {
        # Qué id del lado B va en cada campo.
        "opportunity_id": b.opportunity.pk,
        "client_id": b.client.pk,
        "application_id": b.application.pk,
        "package_job_id": b.package_job.pk,
        "corrects_response_id": b.response.pk,
        "document_file_id": b.file.pk,
    }


def _ready_slot(side: Any) -> ApplicationDocumentSlot:
    slot = (
        ApplicationDocumentSlot.objects.filter(application=side.ready, current_file__isnull=False)
        .order_by("sort_order", "slot_index")
        .first()
    )
    assert slot is not None
    return slot


def _fill(body: dict[str, Any], value: str) -> dict[str, Any]:
    return json.loads(json.dumps(body).replace("{ID}", value))


BODY_CASE_IDS = [
    "applications-opportunity_id",
    "participants-client_id",
    "opportunities-client_id",
    "opportunities-client_id-broker",
    "tasks-application_id",
    "tasks-opportunity_id",
    "filings-package_job_id",
    "responses-corrects_response_id",
    "review-document_file_id",
]


@pytest.mark.parametrize("index", range(len(BODY_CASE_IDS)), ids=BODY_CASE_IDS)
def test_foreign_id_in_body_behaves_like_a_missing_id(world: World, index: int) -> None:
    cases, b_values = _body_cases(world)
    actor, operation, url, body, field = cases[index]
    client = client_for(world, actor)

    foreign = send(client, operation, url, _fill(body, str(b_values[field])))
    missing = send(client, operation, url, _fill(body, str(uuid.uuid4())))

    assert not 200 <= foreign.status_code < 300, foreign.content
    assert (foreign.status_code, _code(foreign)) == (missing.status_code, _code(missing)), (
        foreign.content,
        missing.content,
    )
    assert not _mentions(foreign, *_b_ids(world)), foreign.content
    # El rechazo es por el id (no por otro dato del cuerpo): si no, el caso no prueba nada.
    assert field in _fields(foreign), foreign.content


def test_foreign_slot_in_return_observations_behaves_like_a_missing_slot(world: World) -> None:
    """`observations[].document_slot_id` solo va en una devolución (`RETURNED`), que pide
    una radicación en revisión: se radica la solicitud lista del lado A dentro de la prueba."""
    a = world.a
    filing = create_filing(
        a.advisor,
        a.ready,
        bank_product_id=a.ready.bank_product_id,  # type: ignore[arg-type]
        package_job_id=a.ready_package.pk,
        channel=_item("filing_channel", "BANK_PORTAL"),
        filed_at=timezone.now(),
        expected_version=a.ready.version,
    )
    version = CreditApplication.objects.get(pk=a.ready.pk).version
    url = f"{API}/filings/{filing.pk}/responses"
    operation = "POST /api/v1/filings/{filing_id}/responses"

    def body(slot_id: Any) -> dict[str, Any]:
        return {
            "response_type": "RETURNED",
            "received_at": timezone.now().isoformat(),
            "reason_code": "DOCUMENT_CORRECTION",
            "public_message": "Actualiza el documento.",
            "observations": [
                {"document_slot_id": str(slot_id), "reason_code": "OUTDATED", "message": "x"}
            ],
            "expected_version": version,
        }

    client = client_for(world, ADVISOR_OWNER)
    foreign = send(client, operation, url, body(world.b.slot.pk))
    missing = send(client, operation, url, body(uuid.uuid4()))
    assert not 200 <= foreign.status_code < 300, foreign.content
    assert (foreign.status_code, _code(foreign)) == (missing.status_code, _code(missing))
    assert "observations" in " ".join(_fields(foreign)), foreign.content
    own = send(client, operation, url, body(_ready_slot(a).pk))
    assert own.status_code == 201, own.content


def test_task_for_own_application_can_be_assigned_to_another_advisor(world: World) -> None:
    """API §15: `assigned_to_id` debe ser un usuario activo con rol ADMIN o ADVISOR. Asignar
    a otro asesor una tarea de una solicitud propia está permitido (no es brecha); se deja
    aquí para que un cambio de regla sea visible."""
    client = client_for(world, ADVISOR_OWNER)
    response = client.post(
        f"{API}/tasks",
        {
            "title": "Revisar con Andrés",
            "application_id": str(world.a.application.pk),
            "assigned_to_id": str(world.b.advisor.pk),
        },
        format="json",
    )
    assert response.status_code == 201, response.content


def test_contract_has_no_other_foreign_id_fields_in_bodies() -> None:
    """Spec §3.4 nombra `participant_id`, `filing_id`, `slot_id`, `assigned_to` y
    `beneficiary_user_id` en el cuerpo. Hoy el contrato no tiene esos campos en ninguna
    escritura (el slot va en `observations[].document_slot_id`, la tarea usa
    `assigned_to_id`): si aparecen, hace falta un caso más arriba."""
    spec = json.loads(
        (__import__("tests.security.requests", fromlist=["CONTRACT"]).CONTRACT).read_text(
            encoding="utf-8"
        )
    )
    schemas = spec["components"]["schemas"]
    found = set()
    for item in spec["paths"].values():
        for method in ("post", "put", "patch"):
            content = item.get(method, {}).get("requestBody", {}).get("content", {})
            for media in content.values():
                ref = media.get("schema", {}).get("$ref", "")
                props = schemas.get(ref.rsplit("/", 1)[-1], {}).get("properties", {})
                found |= set(props) & {
                    "participant_id",
                    "filing_id",
                    "slot_id",
                    "assigned_to",
                    "beneficiary_user_id",
                }
    assert found == set()


# --- 2. Comprador A con ids del comprador B --------------------------------------------


def test_buyer_cannot_reach_other_buyer_resources(world: World) -> None:
    client = client_for(world, BUYER_OWNER)
    b = world.b
    notification = Notification.objects.get(pk=b.notification.pk)
    responses = {
        "application": client.get(f"{API}/buyer/applications/{b.application.pk}"),
        "download": client.get(f"{API}/buyer/document-files/{b.file.pk}/download"),
        "read": client.patch(f"{API}/buyer/notifications/{b.notification.pk}/read"),
    }
    assert {name: r.status_code for name, r in responses.items()} == {
        "application": 404,
        "download": 404,
        "read": 404,
    }
    notification.refresh_from_db()
    assert notification.read_at is None


# --- 3. Filtros de listados con ids de otro alcance ------------------------------------

LIST_FILTERS_WITHOUT_FOREIGN_DATA = [
    # (actor, url): 200 sin nada del lado B (alcance; el filtro no lo amplía).
    (ADVISOR_OWNER, "/applications?advisor_id={b_advisor}"),
    (ADVISOR_OWNER, "/applications/quick-filters?advisor_id={b_advisor}"),
    (ADVISOR_OWNER, "/opportunities?advisor_id={b_advisor}"),
    (ADVISOR_OWNER, "/opportunities?client_id={b_client}"),
    (ADVISOR_OWNER, "/opportunities?broker_id={b_broker}"),
    (ADVISOR_OWNER, "/tasks?application_id={b_application}"),
    (ADVISOR_OWNER, "/tasks?opportunity_id={b_opportunity}"),
    (ADVISOR_OWNER, "/tasks?assigned_to_id={b_advisor}"),
    # API §14: "si [el asesor] manda `advisor_id`, se ignora".
    (ADVISOR_OWNER, "/workday/applications?advisor_id={b_advisor}"),
    (ADVISOR_OWNER, "/workday/summary?advisor_id={b_advisor}"),
    (ADVISOR_OWNER, "/applications/{a_application}/document-slots?participant_id={b_participant}"),
    (BROKER_OWNER, "/applications?advisor_id={b_advisor}"),
    (BROKER_OWNER, "/opportunities?broker_id={b_broker}"),
    (BROKER_OWNER, "/opportunities?client_id={b_client}"),
    (BROKER_OWNER, "/broker/opportunities"),
    (PARTNER, "/projects?partner_id={b_partner}"),
]

# API §22: "Los filtros fuera del alcance del usuario retornan 403, no resultados vacíos".
REPORT_FILTERS_FORBIDDEN = [
    "/reports/applications?advisor_id={b_advisor}",
    "/reports/applications.csv?advisor_id={b_advisor}",
    "/reports/funnel?advisor_id={b_advisor}",
    "/dashboard/summary?advisor_id={b_advisor}",
    "/dashboard/funnel?advisor_id={b_advisor}",
    "/dashboard/bank-results?advisor_id={b_advisor}",
    "/dashboard/workload?advisor_id={b_advisor}",
]


def _format(world: World, template: str) -> str:
    b = world.b
    return API + template.format(
        b_advisor=b.advisor.pk,
        b_broker=b.broker.pk,
        b_client=b.client.pk,
        b_application=b.application.pk,
        b_opportunity=b.opportunity.pk,
        b_participant=b.participant.pk,
        b_partner=world.partner_b.pk,
        a_application=world.a.application.pk,
    )


@pytest.mark.parametrize(("actor", "template"), LIST_FILTERS_WITHOUT_FOREIGN_DATA)
def test_list_filter_never_returns_foreign_data(world: World, actor: str, template: str) -> None:
    response = client_for(world, actor).get(_format(world, template))
    assert response.status_code in (200, 403), response.content
    assert not _mentions(response, *_b_ids(world), world.project_b.pk), response.content[:500]


@pytest.mark.parametrize("template", REPORT_FILTERS_FORBIDDEN)
def test_report_filter_out_of_scope_is_forbidden(world: World, template: str) -> None:
    response = client_for(world, ADVISOR_OWNER).get(_format(world, template))
    assert response.status_code == 403, response.content[:300]


def test_export_job_filter_out_of_scope_is_forbidden(world: World) -> None:
    today = timezone.localdate().isoformat()
    response = client_for(world, ADVISOR_OWNER).post(
        f"{API}/reports/applications/export-jobs",
        {"date_from": today, "date_to": today, "advisor_id": str(world.b.advisor.pk)},
        format="json",
    )
    assert response.status_code == 403, response.content


# --- 4. Broker en el detalle de su propia solicitud ------------------------------------


@pytest.mark.parametrize("suffix", ["", "/summary"])
def test_broker_sees_only_the_summary_of_his_application(world: World, suffix: str) -> None:
    response = client_for(world, BROKER_OWNER).get(
        f"{API}/applications/{world.a.application.pk}{suffix}"
    )
    assert response.status_code == 200, response.content
    assert set(response.json()) <= m.BROKER_APPLICATION_SUMMARY_FIELDS, set(response.json())


# --- 5. La constructora en las rutas de expedientes ------------------------------------

DOSSIER_PREFIXES = (
    "/api/v1/applications",
    "/api/v1/application-participants",
    "/api/v1/document-files",
    "/api/v1/document-slots",
    "/api/v1/document-package-jobs",
    "/api/v1/filings",
    "/api/v1/filing-responses",
    "/api/v1/financial-profiles",
    "/api/v1/income-sources",
    "/api/v1/clients",
    "/api/v1/client-addresses",
    "/api/v1/opportunities",
)


def test_partner_never_reaches_dossier_routes(world: World) -> None:
    client = client_for(world, PARTNER)
    reached = {}
    for operation in contract_operations():
        path = operation.split(" ", 1)[1]
        if path.startswith(DOSSIER_PREFIXES):
            for side in ("a", "b"):
                ids = {} if side == "a" else {"application_id": str(world.b.application.pk)}
                status = send(client, operation, url_for(world, operation, ids)).status_code
                if status not in (403, 404):
                    reached[f"{operation} ({side})"] = status
    assert reached == {}


def test_partner_cannot_see_other_partner(world: World) -> None:
    client = client_for(world, PARTNER)
    b_partner, b_project = world.partner_b.pk, world.project_b.pk
    statuses = {
        "partner": client.get(f"{API}/partners/{b_partner}").status_code,
        "members": client.get(f"{API}/partners/{b_partner}/members").status_code,
        "project": client.get(f"{API}/projects/{b_project}").status_code,
        "project_patch": client.patch(
            f"{API}/projects/{b_project}", {"description": "x"}, format="json"
        ).status_code,
    }
    assert statuses == {"partner": 404, "members": 404, "project": 404, "project_patch": 404}


# --- 6. Usuario desactivado o sin rol con la cookie vigente ----------------------------


def test_deactivated_user_with_live_access_cookie_is_rejected(world: World) -> None:
    client = client_for(world, ADVISOR_OWNER)
    assert client.get(f"{API}/auth/me").status_code == 200
    user = world.users[ADVISOR_OWNER]
    user.is_active = False
    user.save(update_fields=["is_active"])
    response = client.get(f"{API}/applications/{world.a.application.pk}")
    assert response.status_code == 401, response.content


def test_user_without_role_loses_access_on_the_next_request(world: World) -> None:
    client = client_for(world, ADVISOR_OWNER)
    url = f"{API}/applications/{world.a.application.pk}"
    assert client.get(url).status_code == 200
    UserRole.objects.filter(user=world.users[ADVISOR_OWNER]).delete()
    response = client.get(url)
    assert response.status_code == 403, response.content
