import uuid
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalogs import services
from apps.catalogs.models import WorkflowTransition
from apps.identity.models import Permission, User
from tests.helpers import assert_error, login

pytestmark = pytest.mark.django_db

TRANSITIONS_URL = "/api/v1/workflow-transitions"

VALID_TRANSITION = {
    "flow_type": "APPLICATION",
    "code": "MARK_READY_TO_FILE",
    "from_status": "DOCUMENTS_REVIEW",
    "to_status": "READY_TO_FILE",
    "label": "Marcar lista para radicar",
    "guard_code": "APPLICATION_READY_TO_FILE",
    "required_permission": "catalogs.read",
    "roles": ["ADVISOR", "ADMIN"],
}


@pytest.fixture(autouse=True)
def _application_flow_without_seeds(db: Any) -> None:
    """Estas pruebas ejercitan el motor genérico sobre un flujo vacío.

    El módulo applications siembra sus propias transiciones (cubiertas en
    `tests/applications/test_seed.py`); aquí se retiran para que no interfieran.
    """
    WorkflowTransition.objects.filter(flow_type="APPLICATION").delete()


def transition_url(transition_id: str) -> str:
    return f"{TRANSITIONS_URL}/{transition_id}"


def create(client: APIClient, **overrides: Any) -> Any:
    return client.post(TRANSITIONS_URL, {**VALID_TRANSITION, **overrides})


def test_create_transition_is_inactive(admin_client: APIClient) -> None:
    response = create(admin_client)

    assert response.status_code == 201
    body = response.json()
    assert body["is_active"] is False
    assert body["roles"] == ["ADMIN", "ADVISOR"]
    assert body["required_permission"] == "catalogs.read"
    assert body["guard_code"] == "APPLICATION_READY_TO_FILE"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"from_status": "NOT_A_STATUS"}, "from_status"),
        ({"to_status": "CONVERTED"}, "to_status"),  # Estado de otro flujo.
        ({"to_status": "DOCUMENTS_REVIEW"}, "to_status"),  # Igual al origen.
        ({"guard_code": "INVENTED_GUARD"}, "guard_code"),
        ({"required_permission": "no.existe"}, "required_permission"),
        ({"roles": ["SUPERHERO"]}, "roles"),
        ({"roles": []}, "roles"),
        ({"flow_type": "INVOICE"}, "flow_type"),
        ({"code": "minusculas"}, "code"),
    ],
)
def test_create_transition_validates_input(
    admin_client: APIClient, overrides: dict[str, Any], field: str
) -> None:
    body = assert_error(create(admin_client, **overrides), 400, "VALIDATION_ERROR")
    assert field in {detail["field"] for detail in body["details"]}


def test_create_transition_rejects_duplicate_code_in_flow(admin_client: APIClient) -> None:
    create(admin_client)
    assert_error(create(admin_client), 409, "DUPLICATE_CODE")


def test_same_code_is_allowed_in_another_flow(admin_client: APIClient) -> None:
    create(admin_client)
    response = create(
        admin_client,
        flow_type="PROJECT",
        from_status="DRAFT",
        to_status="PENDING_REVIEW",
        guard_code=None,
    )
    assert response.status_code == 201


def test_update_inactive_transition(admin_client: APIClient) -> None:
    transition_id = create(admin_client).json()["id"]

    response = admin_client.patch(
        transition_url(transition_id),
        {"label": "Lista para radicar", "roles": ["ADVISOR"], "guard_code": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Lista para radicar"
    assert body["roles"] == ["ADVISOR"]
    assert body["guard_code"] is None


def test_update_validates_states_against_the_existing_flow(admin_client: APIClient) -> None:
    transition_id = create(admin_client).json()["id"]
    response = admin_client.patch(transition_url(transition_id), {"to_status": "CONVERTED"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_flow_type_and_code_cannot_be_changed(admin_client: APIClient) -> None:
    transition_id = create(admin_client).json()["id"]
    response = admin_client.patch(transition_url(transition_id), {"code": "OTRO"})
    assert_error(response, 400, "VALIDATION_ERROR")


def test_active_transition_cannot_be_edited(admin_client: APIClient) -> None:
    transition_id = create(admin_client).json()["id"]
    assert admin_client.post(f"{transition_url(transition_id)}/activate").status_code == 200

    response = admin_client.patch(transition_url(transition_id), {"label": "Otro"})
    assert_error(response, 409, "TRANSITION_NOT_EDITABLE")

    admin_client.post(f"{transition_url(transition_id)}/deactivate")
    assert admin_client.patch(transition_url(transition_id), {"label": "Otro"}).status_code == 200


def test_activation_requires_publish_permission(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    transition_id = create(admin_client).json()["id"]
    make_user(
        email="editor@example.com",
        role_code="ADVISOR",
        permissions=["workflow.read", "workflow.create", "workflow.update"],
    )
    editor = APIClient()
    login(editor, email="editor@example.com")

    assert editor.get(transition_url(transition_id)).status_code == 200
    response = editor.post(f"{transition_url(transition_id)}/activate")
    assert_error(response, 403, "PERMISSION_DENIED")


def test_list_transitions_with_filters(admin_client: APIClient) -> None:
    create(admin_client)
    create(
        admin_client,
        flow_type="OPPORTUNITY",
        code="CONTACT",
        from_status="ASSIGNED",
        to_status="CONTACTED",
        guard_code=None,
    )

    body = admin_client.get(
        TRANSITIONS_URL, {"flow_type": "OPPORTUNITY", "is_active": "false"}
    ).json()
    assert [item["code"] for item in body["items"]] == ["CONTACT"]

    # Las creadas por API nacen inactivas; las activas son las sembradas por las migraciones.
    body = admin_client.get(TRANSITIONS_URL, {"is_active": "false"}).json()
    assert {item["code"] for item in body["items"]} == {"CONTACT", "MARK_READY_TO_FILE"}
    body = admin_client.get(TRANSITIONS_URL, {"is_active": "true", "page_size": "100"}).json()
    assert {item["flow_type"] for item in body["items"]} == {"PROJECT", "OPPORTUNITY"}

    assert_error(
        admin_client.get(TRANSITIONS_URL, {"flow_type": "INVOICE"}), 400, "VALIDATION_ERROR"
    )


def test_retrieve_unknown_transition_returns_404(admin_client: APIClient) -> None:
    assert_error(admin_client.get(transition_url(str(uuid.uuid4()))), 404, "RESOURCE_NOT_FOUND")


def test_transitions_require_permission(advisor_client: APIClient) -> None:
    assert_error(advisor_client.get(TRANSITIONS_URL), 403, "PERMISSION_DENIED")


# --- Transiciones disponibles para un usuario ------------------------------------------


@pytest.fixture
def published_transition(admin_client: APIClient) -> WorkflowTransition:
    # Código de prueba: el motor es genérico y no depende de los permisos sembrados.
    Permission.objects.create(code="workflow_test.review", module="workflow_test", name="Revisar")
    body = create(
        admin_client, required_permission="workflow_test.review", roles=["ADVISOR"]
    ).json()
    admin_client.post(f"{transition_url(body['id'])}/activate")
    return WorkflowTransition.objects.get(pk=body["id"])


def _available(user: User) -> list[str]:
    return list(
        services.available_transitions(
            user, flow_type="APPLICATION", from_status="DOCUMENTS_REVIEW"
        ).values_list("code", flat=True)
    )


def test_available_transitions_require_role_and_permission(
    published_transition: WorkflowTransition, make_user: Callable[..., User]
) -> None:
    with_permission = make_user(
        email="con@example.com", role_code="ADVISOR", permissions=["workflow_test.review"]
    )
    assert _available(with_permission) == ["MARK_READY_TO_FILE"]

    broker = make_user(
        email="broker@example.com",
        role_code="INDEPENDENT_BROKER",
        permissions=["workflow_test.review"],
    )
    assert _available(broker) == []


def test_available_transitions_require_the_permission(
    make_user: Callable[..., User], admin_client: APIClient
) -> None:
    Permission.objects.create(code="filings.manage", module="filings", name="Radicar")
    body = create(admin_client, required_permission="filings.manage", roles=["ADVISOR"]).json()
    admin_client.post(f"{transition_url(body['id'])}/activate")

    advisor = make_user(email="sin@example.com", role_code="ADVISOR")
    assert _available(advisor) == []


def test_admin_does_not_need_to_be_listed_in_roles(
    published_transition: WorkflowTransition, make_user: Callable[..., User]
) -> None:
    admin = make_user(email="otro-admin@example.com", role_code="ADMIN")
    # El ADMIN necesita el permiso de la transición igual que los demás.
    assert _available(admin) == []

    superuser = make_user(email="root@example.com", role_code=None, is_superuser=True)
    assert _available(superuser) == ["MARK_READY_TO_FILE"]


def test_inactive_transitions_are_not_available(
    admin_client: APIClient, make_user: Callable[..., User]
) -> None:
    create(admin_client, required_permission=None, roles=["ADVISOR"])
    advisor = make_user(email="a2@example.com", role_code="ADVISOR")
    assert _available(advisor) == []
