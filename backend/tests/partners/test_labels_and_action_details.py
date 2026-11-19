"""Constructoras y proyectos (TAREA-brechas-3-demo, parte 1): `status_label` en partner y
membresía, y `available_action_details` en el detalle del proyecto con la etiqueta, el
tipo y el motivo de cada acción (misma forma que `AvailableAction` de la solicitud)."""

from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalogs.workflow import ProjectStatus
from apps.partners.actions import ACTION_KIND_BY_TARGET_STATUS
from apps.partners.models import Partner, PartnerMembership, Project
from tests.partners.test_partners_api import PARTNERS_URL, members_url, partner_url
from tests.partners.test_projects_api import project_url

pytestmark = pytest.mark.django_db


def details(body: dict[str, Any]) -> list[tuple[str, str, str, str, bool]]:
    return [
        (
            action["code"],
            action["label"],
            action["kind"],
            action["target_status_label"],
            action["reason_required"],
        )
        for action in body["available_action_details"]
    ]


# --- Estados de partner y membresía ------------------------------------------------------


def test_partner_and_membership_bring_the_label_of_their_status(
    admin_client: APIClient,
    partner: Partner,
    other_partner: Partner,
    partner_user: Any,
) -> None:
    other_partner.status = "INACTIVE"
    other_partner.save()

    listed = {
        item["legal_name"]: item["status_label"]
        for item in admin_client.get(PARTNERS_URL).json()["items"]
    }
    assert listed == {partner.legal_name: "Activo", other_partner.legal_name: "Inactivo"}
    assert admin_client.get(partner_url(partner)).json()["status_label"] == "Activo"

    member = admin_client.get(members_url(partner)).json()["items"][0]
    assert (member["status"], member["status_label"]) == ("ACTIVE", "Activo")
    membership = PartnerMembership.objects.get(user=partner_user)
    membership.status = "INACTIVE"
    membership.save()
    member = admin_client.get(members_url(partner)).json()["items"][0]
    assert member["status_label"] == "Inactivo"


def test_the_partner_list_queries_do_not_grow(
    admin_client: APIClient, make_partner: Callable[..., Partner]
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert admin_client.get(PARTNERS_URL).status_code == 200
        return len(queries)

    make_partner()
    one = measure()
    for index in range(4):
        make_partner(legal_name=f"Constructora {index} S.A.S.", tax_id=f"90012345{index}-1")

    assert measure() == one


# --- Acciones del proyecto con etiqueta --------------------------------------------------


def test_every_project_status_has_a_kind() -> None:
    assert set(ACTION_KIND_BY_TARGET_STATUS) == set(ProjectStatus.values)


def test_project_detail_brings_the_actions_with_label_kind_and_reason(
    admin_client: APIClient,
    advisor_client: APIClient,
    partner_client: APIClient,
    partner: Partner,
    make_project: Callable[..., Project],
) -> None:
    draft = make_project(partner)
    pending = make_project(partner, name="Altos", status=ProjectStatus.PENDING_REVIEW)

    body = admin_client.get(project_url(draft)).json()
    # El campo de siempre no cambia: códigos por orden alfabético.
    assert body["available_actions"] == ["APPROVE_DRAFT", "ARCHIVE_DRAFT", "SUBMIT_FOR_REVIEW"]
    # El nuevo: principales, secundarias y destructivas.
    assert details(body) == [
        ("APPROVE_DRAFT", "Aprobar sin enviar a validación", "primary", "Activo", False),
        ("SUBMIT_FOR_REVIEW", "Enviar a validación", "primary", "En validación", False),
        ("ARCHIVE_DRAFT", "Archivar", "destructive", "Archivado", True),
    ]
    action = body["available_action_details"][0]
    assert set(action) == {
        "code",
        "label",
        "kind",
        "target_status",
        "target_status_label",
        "reason_required",
    }
    assert action["target_status"] == "ACTIVE"

    assert details(advisor_client.get(project_url(pending)).json()) == [
        ("APPROVE", "Aprobar", "primary", "Activo", False),
        ("REJECT", "Devolver a borrador", "secondary", "Borrador", True),
    ]
    assert details(partner_client.get(project_url(draft)).json()) == [
        ("SUBMIT_FOR_REVIEW", "Enviar a validación", "primary", "En validación", False),
    ]


def test_transitions_answer_the_details_too(
    partner_client: APIClient, partner: Partner, make_project: Callable[..., Project]
) -> None:
    project = make_project(partner)

    body = partner_client.post(f"{project_url(project)}/submit").json()

    assert body["status"] == "PENDING_REVIEW"
    assert body["available_actions"] == []
    assert body["available_action_details"] == []
