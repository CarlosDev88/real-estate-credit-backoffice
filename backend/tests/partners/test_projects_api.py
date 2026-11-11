import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalogs.models import CatalogItem, WorkflowTransition
from apps.identity.models import User
from apps.partners import services
from apps.partners.exceptions import ProjectNotActive
from apps.partners.models import Partner, PartnerMembership, Project
from tests.helpers import assert_error

pytestmark = pytest.mark.django_db

PROJECTS_URL = "/api/v1/projects"

VALID_PROJECT = {
    "name": "Verona 118",
    "city_code": "11001",
    "address": "Carrera 11 # 118-40",
    "description": "Proyecto de vivienda nueva",
    "estimated_delivery_date": "2027-06-30",
}


def project_url(project: Project | str) -> str:
    project_id = project if isinstance(project, str) else project.id
    return f"{PROJECTS_URL}/{project_id}"


# --- Crear ------------------------------------------------------------------------------


def test_partner_user_creates_draft_project_for_own_partner(
    partner_client: APIClient, partner: Partner
) -> None:
    response = partner_client.post(PROJECTS_URL, VALID_PROJECT)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["partner"]["id"] == str(partner.id)
    assert body["city"] == {
        "code": "11001",
        "label": "Bogotá, D.C.",
        "department_code": "11",
        "department_label": "Bogotá, D.C.",
    }
    assert body["created_by"]["name"] == "Andrea García"
    assert body["validated_by"] is None
    assert body["available_actions"] == ["SUBMIT_FOR_REVIEW"]


def test_partner_user_cannot_create_for_another_partner(
    partner_client: APIClient, partner: Partner, other_partner: Partner
) -> None:
    """RF-15: el partner se deriva de la membresía; un `partner_id` ajeno se ignora."""
    response = partner_client.post(
        PROJECTS_URL, {**VALID_PROJECT, "partner_id": str(other_partner.id)}
    )
    assert response.status_code == 201
    assert response.json()["partner"]["id"] == str(partner.id)


def test_partner_user_without_membership_cannot_create(make_user: Callable[..., User]) -> None:
    from tests.partners.conftest import client_for

    user = make_user(email="sin@example.com", role_code="CONSTRUCTION_PARTNER")
    response = client_for(user).post(PROJECTS_URL, VALID_PROJECT)
    assert_error(response, 403, "OUT_OF_SCOPE")


def test_inactive_partner_cannot_create_projects(
    partner_client: APIClient, partner: Partner
) -> None:
    partner.status = "INACTIVE"
    partner.save()
    assert_error(partner_client.post(PROJECTS_URL, VALID_PROJECT), 422, "PARTNER_NOT_ACTIVE")


def test_advisor_creates_project_with_partner_id(
    advisor_client: APIClient, partner: Partner
) -> None:
    response = advisor_client.post(PROJECTS_URL, {**VALID_PROJECT, "partner_id": str(partner.id)})
    assert response.status_code == 201
    assert response.json()["partner"]["id"] == str(partner.id)


def test_advisor_must_send_an_existing_partner(advisor_client: APIClient) -> None:
    body = assert_error(advisor_client.post(PROJECTS_URL, VALID_PROJECT), 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "partner_id"

    response = advisor_client.post(PROJECTS_URL, {**VALID_PROJECT, "partner_id": str(uuid.uuid4())})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_broker_cannot_create_projects(broker_client: APIClient, partner: Partner) -> None:
    response = broker_client.post(PROJECTS_URL, {**VALID_PROJECT, "partner_id": str(partner.id)})
    assert_error(response, 403, "PERMISSION_DENIED")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("city_code", "99999"),  # No existe en el catálogo.
        ("city_code", "11"),  # Es un departamento, no un municipio.
        ("address", ""),
        ("name", ""),
        ("estimated_delivery_date", "30/06/2027"),
    ],
)
def test_create_project_validates_input(partner_client: APIClient, field: str, value: str) -> None:
    body = assert_error(
        partner_client.post(PROJECTS_URL, {**VALID_PROJECT, field: value}), 400, "VALIDATION_ERROR"
    )
    assert body["details"][0]["field"] == field


def test_project_name_is_unique_per_partner_while_open(
    partner_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    make_project(other_partner)  # Mismo nombre en otra constructora: permitido.
    assert partner_client.post(PROJECTS_URL, VALID_PROJECT).status_code == 201

    response = partner_client.post(PROJECTS_URL, {**VALID_PROJECT, "name": "VERONA 118"})
    assert_error(response, 409, "DUPLICATE_PROJECT_NAME")

    # Archivar libera el nombre.
    Project.objects.filter(partner=partner).update(status="ARCHIVED")
    assert partner_client.post(PROJECTS_URL, VALID_PROJECT).status_code == 201


def test_project_code_is_unique_per_partner(partner_client: APIClient) -> None:
    partner_client.post(PROJECTS_URL, {**VALID_PROJECT, "code": "VER-01"})
    response = partner_client.post(
        PROJECTS_URL, {**VALID_PROJECT, "name": "Otro", "code": "VER-01"}
    )
    assert_error(response, 409, "DUPLICATE_PROJECT_NAME")

    # Sin código no hay conflicto.
    assert partner_client.post(PROJECTS_URL, {**VALID_PROJECT, "name": "A"}).status_code == 201
    response = partner_client.post(PROJECTS_URL, {**VALID_PROJECT, "name": "B", "code": ""})
    assert response.status_code == 201


# --- Consultar y alcance ----------------------------------------------------------------


def test_partner_user_only_sees_own_projects(
    partner_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    own = make_project(partner)
    foreign = make_project(other_partner, name="Ajeno")

    body = partner_client.get(PROJECTS_URL).json()
    assert [item["id"] for item in body["items"]] == [str(own.id)]
    assert_error(partner_client.get(project_url(foreign)), 404, "RESOURCE_NOT_FOUND")
    # Filtrar por el partner ajeno no amplía el alcance.
    body = partner_client.get(PROJECTS_URL, {"partner_id": str(other_partner.id)}).json()
    assert body["items"] == []


def test_broker_only_sees_active_projects_of_active_partners(
    broker_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    active = make_project(partner, status="ACTIVE")
    make_project(partner, name="Borrador")
    make_project(other_partner, name="De partner inactivo", status="ACTIVE")
    other_partner.status = "INACTIVE"
    other_partner.save()

    body = broker_client.get(PROJECTS_URL).json()
    assert [item["id"] for item in body["items"]] == [str(active.id)]
    assert broker_client.get(project_url(active)).json()["available_actions"] == []


def test_advisor_sees_all_projects(
    advisor_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    make_project(partner)
    make_project(other_partner, name="Otro")
    assert advisor_client.get(PROJECTS_URL).json()["total"] == 2


def test_list_projects_filters(
    admin_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    make_project: Callable[..., Project],
    medellin: CatalogItem,
) -> None:
    make_project(partner, status="ACTIVE")
    make_project(partner, name="Medellín", city_item=medellin)
    make_project(other_partner, name="Otro")

    assert admin_client.get(PROJECTS_URL, {"status": "ACTIVE"}).json()["total"] == 1
    assert admin_client.get(PROJECTS_URL, {"city_code": "05001"}).json()["total"] == 1
    assert admin_client.get(PROJECTS_URL, {"partner_id": str(partner.id)}).json()["total"] == 2
    assert admin_client.get(PROJECTS_URL, {"search": "medell"}).json()["total"] == 1
    assert_error(admin_client.get(PROJECTS_URL, {"status": "X"}), 400, "VALIDATION_ERROR")
    assert_error(admin_client.get(PROJECTS_URL, {"partner_id": "x"}), 400, "VALIDATION_ERROR")


# --- Editar -----------------------------------------------------------------------------


def test_partner_user_edits_draft_project(
    partner_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner)

    response = partner_client.patch(project_url(project), {"city_code": "05001", "code": "V-1"})

    assert response.status_code == 200
    assert response.json()["city"]["code"] == "05001"
    assert response.json()["code"] == "V-1"


def test_partner_user_cannot_edit_after_draft(
    partner_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner, status="PENDING_REVIEW")
    response = partner_client.patch(project_url(project), {"name": "Otro"})
    assert_error(response, 409, "PROJECT_NOT_EDITABLE")


def test_advisor_can_correct_an_active_project(
    advisor_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner, status="ACTIVE")
    response = advisor_client.patch(project_url(project), {"address": "Calle 1 # 2-3"})
    assert response.status_code == 200


def test_archived_projects_are_read_only(
    admin_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner, status="ARCHIVED")
    response = admin_client.patch(project_url(project), {"name": "Otro"})
    assert_error(response, 409, "PROJECT_NOT_EDITABLE")


def test_project_partner_and_status_cannot_be_patched(
    admin_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner)
    for payload in ({"status": "ACTIVE"}, {"partner_id": str(partner.id)}):
        assert_error(admin_client.patch(project_url(project), payload), 400, "VALIDATION_ERROR")


# --- Flujo de estados -------------------------------------------------------------------


def test_full_project_lifecycle(
    partner_client: APIClient, advisor_client: APIClient, admin_client: APIClient, partner: Partner
) -> None:
    project_id = partner_client.post(PROJECTS_URL, VALID_PROJECT).json()["id"]

    body = partner_client.post(f"{project_url(project_id)}/submit").json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["available_actions"] == []  # La constructora ya no puede actuar.

    assert advisor_client.get(project_url(project_id)).json()["available_actions"] == [
        "APPROVE",
        "REJECT",
    ]
    body = advisor_client.post(f"{project_url(project_id)}/activate").json()
    assert body["status"] == "ACTIVE"
    assert body["validated_by"]["name"] == "Andrea García"
    assert body["validated_at"] is not None

    body = admin_client.post(f"{project_url(project_id)}/archive", {"reason": "Vendido"}).json()
    assert body["status"] == "ARCHIVED"


def test_reject_returns_to_draft_and_requires_reason(
    partner_client: APIClient, advisor_client: APIClient, partner: Partner
) -> None:
    project_id = partner_client.post(PROJECTS_URL, VALID_PROJECT).json()["id"]
    partner_client.post(f"{project_url(project_id)}/submit")

    url = f"{project_url(project_id)}/reject"
    assert_error(advisor_client.post(url, {}), 400, "VALIDATION_ERROR")
    body = advisor_client.post(url, {"reason": "Falta la dirección exacta"}).json()
    assert body["status"] == "DRAFT"

    # De vuelta en borrador, la constructora puede corregir y reenviar.
    assert partner_client.patch(project_url(project_id), {"name": "Verona"}).status_code == 200


def test_advisor_can_approve_a_draft_directly(
    advisor_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner)
    assert advisor_client.post(f"{project_url(project)}/activate").json()["status"] == "ACTIVE"


def test_partner_user_cannot_approve(
    partner_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner, status="PENDING_REVIEW")
    response = partner_client.post(f"{project_url(project)}/activate")
    assert_error(response, 403, "PERMISSION_DENIED")


def test_advisor_cannot_archive(
    advisor_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner, status="ACTIVE")
    response = advisor_client.post(f"{project_url(project)}/archive", {"reason": "x"})
    assert_error(response, 403, "PERMISSION_DENIED")


def test_invalid_transitions_return_409(
    admin_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    archived = make_project(partner, status="ARCHIVED")
    assert_error(
        admin_client.post(f"{project_url(archived)}/activate"), 409, "INVALID_STATE_TRANSITION"
    )
    active = make_project(partner, name="Activo", status="ACTIVE")
    assert_error(
        admin_client.post(f"{project_url(active)}/reject", {"reason": "x"}),
        409,
        "INVALID_STATE_TRANSITION",
    )
    assert_error(
        admin_client.post(f"{project_url(active)}/submit"), 409, "INVALID_STATE_TRANSITION"
    )


def test_deactivated_transition_blocks_the_action(
    admin_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    """La configuración de workflow_transitions decide qué acciones existen."""
    WorkflowTransition.objects.filter(flow_type="PROJECT", code="APPROVE_DRAFT").update(
        is_active=False
    )
    project = make_project(partner)
    assert_error(
        admin_client.post(f"{project_url(project)}/activate"), 409, "INVALID_STATE_TRANSITION"
    )


def test_partner_user_of_inactive_partner_cannot_submit(
    partner_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner)
    partner.status = "INACTIVE"
    partner.save()

    assert partner_client.get(project_url(project)).json()["available_actions"] == []
    assert_error(partner_client.post(f"{project_url(project)}/submit"), 422, "PARTNER_NOT_ACTIVE")


def test_transition_emits_signal_with_reason(
    admin_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    from apps.partners.signals import project_status_changed

    project = make_project(partner, status="ACTIVE")
    received: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    project_status_changed.connect(handler)
    try:
        admin_client.post(f"{project_url(project)}/archive", {"reason": "Entregado"})
    finally:
        project_status_changed.disconnect(handler)

    assert len(received) == 1
    assert received[0]["transition_code"] == "ARCHIVE_ACTIVE"
    assert received[0]["reason"] == "Entregado"


def test_membership_end_removes_access_to_projects(
    partner_client: APIClient,
    partner_user: User,
    partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    project = make_project(partner)
    PartnerMembership.objects.filter(user=partner_user).update(
        status="INACTIVE", ended_at=date.today()
    )
    assert_error(partner_client.get(project_url(project)), 404, "RESOURCE_NOT_FOUND")


# --- Regla para oportunidades (paso 5) --------------------------------------------------


def test_only_active_projects_accept_opportunities(
    partner: Partner, make_project: Callable[..., Project]
) -> None:
    active = make_project(partner, status="ACTIVE")
    services.ensure_project_accepts_opportunities(active)

    for status_code in ("DRAFT", "PENDING_REVIEW", "ARCHIVED"):
        project = make_project(partner, name=status_code, status=status_code)
        with pytest.raises(ProjectNotActive):
            services.ensure_project_accepts_opportunities(project)

    partner.status = "INACTIVE"
    partner.save()
    active.refresh_from_db()
    with pytest.raises(ProjectNotActive):
        services.ensure_project_accepts_opportunities(active)
