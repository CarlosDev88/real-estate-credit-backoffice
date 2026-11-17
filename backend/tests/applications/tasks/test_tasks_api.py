"""Tareas manuales (API §15.2): alcance, creación, edición, cierre, filtros y consultas."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Opportunity
from apps.identity.models import User
from apps.tasks.models import Task, TaskSource, TaskStatus
from apps.tasks.signals import task_cancelled, task_completed, task_created
from tests.applications.conftest import catalog_item
from tests.applications.tasks.conftest import TASKS_URL, task_url
from tests.helpers import assert_error
from tests.partners.conftest import client_for

pytestmark = pytest.mark.django_db

AppFactory = Callable[..., CreditApplication]
OppFactory = Callable[..., Opportunity]
TaskFactory = Callable[..., Task]

# 23:30 del 10 de noviembre en Bogotá; en UTC ya es el 11.
NOW = datetime(2026, 11, 11, 4, 30, tzinfo=UTC)


def codes(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["title"] for item in response.json()["items"]]


def create(client: APIClient, **body: Any) -> Any:
    body.setdefault("title", "Revisar extractos corregidos")
    return client.post(TASKS_URL, body, format="json")


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, sender: Any, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# --- Permisos y alcance -----------------------------------------------------------------


@pytest.mark.parametrize("client_name", ["broker_client", "partner_client"])
def test_broker_and_partner_have_no_tasks(request: pytest.FixtureRequest, client_name: str) -> None:
    client: APIClient = request.getfixturevalue(client_name)

    assert_error(client.get(TASKS_URL), 403, "PERMISSION_DENIED")
    assert_error(create(client), 403, "PERMISSION_DENIED")


def test_advisor_sees_assigned_tasks_and_those_of_their_applications_and_opportunities(
    advisor_client: APIClient,
    advisor_user: User,
    other_advisor: User,
    make_task_application: AppFactory,
    make_task_opportunity: OppFactory,
    make_task: TaskFactory,
) -> None:
    mine = make_task_application()
    theirs = make_task_application(advisor=other_advisor)
    make_task(mine, title="De mi solicitud", assigned_to=other_advisor)
    make_task(theirs, title="Asignada a mí")
    make_task(theirs, title="Ajena", assigned_to=other_advisor)
    make_task(
        opportunity=make_task_opportunity(), title="De mi oportunidad", assigned_to=other_advisor
    )
    captured = make_task_opportunity(advisor=other_advisor, origin_user=advisor_user)
    make_task(
        opportunity=captured, title="De la oportunidad que capturé", assigned_to=other_advisor
    )
    make_task(
        opportunity=make_task_opportunity(advisor=other_advisor),
        title="Oportunidad ajena",
        assigned_to=other_advisor,
    )

    assert sorted(codes(advisor_client.get(TASKS_URL))) == [
        "Asignada a mí",
        "De la oportunidad que capturé",
        "De mi oportunidad",
        "De mi solicitud",
    ]
    hidden = Task.objects.get(title="Ajena")
    assert_error(advisor_client.get(task_url(hidden)), 404, "RESOURCE_NOT_FOUND")


def test_admin_sees_every_task_and_filters_by_assignee(
    admin_client: APIClient,
    advisor_client: APIClient,
    other_advisor: User,
    make_task_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    application = make_task_application(advisor=other_advisor)
    make_task(application, title="Del asesor")
    make_task(application, title="De Marta", assigned_to=other_advisor)

    assert sorted(codes(admin_client.get(TASKS_URL))) == ["De Marta", "Del asesor"]
    filtered = admin_client.get(TASKS_URL, {"assigned_to_id": str(other_advisor.pk)})
    assert codes(filtered) == ["De Marta"]
    # El asesor no filtra por responsable: se ignora.
    ignored = advisor_client.get(TASKS_URL, {"assigned_to_id": str(other_advisor.pk)})
    assert codes(ignored) == ["Del asesor"]


# --- Crear ------------------------------------------------------------------------------


def test_create_with_defaults_returns_the_full_task(
    advisor_client: APIClient,
    advisor_user: User,
    make_task_application: AppFactory,
    django_capture_on_commit_callbacks: Any,
) -> None:
    application = make_task_application()
    recorder = Recorder()
    task_created.connect(recorder)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = create(advisor_client, application_id=str(application.pk))
    finally:
        task_created.disconnect(recorder)

    assert response.status_code == 201, response.content
    body = response.json()
    task = Task.objects.get(pk=body["id"])
    assert body == {
        "id": str(task.pk),
        "title": "Revisar extractos corregidos",
        "description": "",
        "status": "PENDING",
        "status_label": "Pendiente",
        "priority": {"code": "MEDIUM", "label": "Media"},
        "source": "MANUAL",
        "source_label": "Manual",
        "assigned_to": {"id": str(advisor_user.pk), "name": "Andrea García"},
        "created_by": {"id": str(advisor_user.pk), "name": "Andrea García"},
        "parent": {
            "type": "APPLICATION",
            "type_label": "Solicitud",
            "id": str(application.pk),
            "code": application.code,
            "client_display_name": "Sofía Gómez Vélez",
        },
        "due_at": None,
        "is_overdue": False,
        "completed_at": None,
        "cancelled_at": None,
        "cancel_reason": "",
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    assert task.source == TaskSource.MANUAL
    assert [call["task"].pk for call in recorder.calls] == [task.pk]
    assert recorder.calls[0]["actor"] == advisor_user


def test_create_on_an_opportunity_with_every_field(
    advisor_client: APIClient, other_advisor: User, make_task_opportunity: OppFactory
) -> None:
    opportunity = make_task_opportunity()

    response = create(
        advisor_client,
        opportunity_id=str(opportunity.pk),
        description="Pedir los extractos de octubre",
        assigned_to_id=str(other_advisor.pk),
        due_at="2026-12-01T17:00:00Z",
        priority_code="HIGH",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["parent"] == {
        "type": "OPPORTUNITY",
        "type_label": "Oportunidad",
        "id": str(opportunity.pk),
        "code": None,
        "client_display_name": "Sofía Gómez Vélez",
    }
    assert body["assigned_to"]["id"] == str(other_advisor.pk)
    assert body["priority"] == {"code": "HIGH", "label": "Alta"}
    assert body["due_at"] == "2026-12-01T12:00:00-05:00"
    assert body["description"] == "Pedir los extractos de octubre"


@pytest.mark.parametrize("parents", ["none", "both"])
def test_create_needs_exactly_one_parent(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    make_task_opportunity: OppFactory,
    parents: str,
) -> None:
    body: dict[str, Any] = {}
    if parents == "both":
        body = {
            "application_id": str(make_task_application().pk),
            "opportunity_id": str(make_task_opportunity().pk),
        }

    response = create(advisor_client, **body)

    error = assert_error(response, 400, "VALIDATION_ERROR")
    assert error["details"][0]["field"] is None
    assert not Task.objects.exists()


def test_create_rejects_parents_outside_the_scope(
    advisor_client: APIClient,
    other_advisor: User,
    make_task_application: AppFactory,
    make_task_opportunity: OppFactory,
) -> None:
    application = make_task_application(advisor=other_advisor)
    opportunity = make_task_opportunity(advisor=other_advisor)

    by_application = create(advisor_client, application_id=str(application.pk))
    by_opportunity = create(advisor_client, opportunity_id=str(opportunity.pk))

    assert assert_error(by_application, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "application_id"
    )
    assert assert_error(by_opportunity, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "opportunity_id"
    )


def test_create_on_a_closed_application(
    advisor_client: APIClient, make_task_application: AppFactory
) -> None:
    application = make_task_application(ApplicationStatus.WITHDRAWN)

    response = create(advisor_client, application_id=str(application.pk))

    assert_error(response, 409, "APPLICATION_CLOSED")
    assert not Task.objects.exists()


@pytest.mark.parametrize("assignee", ["broker", "inactive", "deleted", "missing"])
def test_create_rejects_an_ineligible_assignee(
    advisor_client: APIClient,
    make_user: Callable[..., User],
    broker_user: User,
    make_task_application: AppFactory,
    assignee: str,
) -> None:
    users = {
        "broker": lambda: broker_user.pk,
        "inactive": lambda: make_user(email="inactivo@example.com", is_active=False).pk,
        "deleted": lambda: make_user(email="borrado@example.com", deleted_at=timezone.now()).pk,
        "missing": lambda: "8f9b8f5e-0000-4000-8000-000000000000",
    }

    response = create(
        advisor_client,
        application_id=str(make_task_application().pk),
        assigned_to_id=str(users[assignee]()),
    )

    error = assert_error(response, 400, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "assigned_to_id"


def test_admin_can_be_the_assignee(
    advisor_client: APIClient, admin_user: User, make_task_application: AppFactory
) -> None:
    response = create(
        advisor_client,
        application_id=str(make_task_application().pk),
        assigned_to_id=str(admin_user.pk),
    )

    assert response.status_code == 201, response.content


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"priority_code": "URGENT"}, "priority_code"),
        ({"title": ""}, "title"),
        ({"title": "x" * 181}, "title"),
        ({"status": "COMPLETED"}, "status"),
    ],
)
def test_create_validates_the_body(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    body: dict[str, Any],
    field: str,
) -> None:
    response = create(advisor_client, application_id=str(make_task_application().pk), **body)

    assert assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == field


# --- Editar -----------------------------------------------------------------------------


def test_patch_changes_the_editable_fields(
    advisor_client: APIClient,
    other_advisor: User,
    make_task_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    task = make_task(make_task_application(), due_at=timezone.now())

    response = advisor_client.patch(
        task_url(task),
        {
            "title": "Llamar de nuevo",
            "description": "Después de las 3",
            "assigned_to_id": str(other_advisor.pk),
            "due_at": None,
            "priority_code": "LOW",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["title"], body["description"], body["due_at"]) == (
        "Llamar de nuevo",
        "Después de las 3",
        None,
    )
    assert body["assigned_to"]["id"] == str(other_advisor.pk)
    assert body["priority"]["code"] == "LOW"
    task.refresh_from_db()
    assert task.assigned_to == other_advisor


def test_patch_with_an_empty_body_changes_nothing(
    advisor_client: APIClient, make_task_application: AppFactory, make_task: TaskFactory
) -> None:
    task = make_task(make_task_application())

    response = advisor_client.patch(task_url(task), {}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["title"] == "Llamar al comprador"


def test_patch_rejects_an_ineligible_assignee(
    advisor_client: APIClient,
    broker_user: User,
    make_task_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    task = make_task(make_task_application())

    response = advisor_client.patch(
        task_url(task), {"assigned_to_id": str(broker_user.pk)}, format="json"
    )

    assert assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == (
        "assigned_to_id"
    )


@pytest.mark.parametrize("status", [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
def test_closed_tasks_are_not_edited_completed_or_cancelled(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    make_task: TaskFactory,
    status: str,
) -> None:
    closed_at = timezone.now()
    extra: dict[str, Any] = (
        {"completed_at": closed_at}
        if status == TaskStatus.COMPLETED
        else {"cancelled_at": closed_at, "cancel_reason": "Ya no aplica"}
    )
    task = make_task(make_task_application(), status=status, **extra)

    patch = advisor_client.patch(task_url(task), {"title": "Otro"}, format="json")
    complete = advisor_client.post(task_url(task, "/complete"))
    cancel = advisor_client.post(task_url(task, "/cancel"), {"reason": "x"}, format="json")

    for response in (patch, complete, cancel):
        assert_error(response, 409, "TASK_NOT_PENDING")
    task.refresh_from_db()
    assert (task.status, task.title) == (status, "Llamar al comprador")


# --- Completar y cancelar ---------------------------------------------------------------


def test_complete_a_pending_task(
    advisor_client: APIClient,
    advisor_user: User,
    make_task_application: AppFactory,
    make_task: TaskFactory,
    django_capture_on_commit_callbacks: Any,
) -> None:
    task = make_task(make_task_application())
    recorder = Recorder()
    task_completed.connect(recorder)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = advisor_client.post(task_url(task, "/complete"))
    finally:
        task_completed.disconnect(recorder)

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["status"], body["status_label"]) == ("COMPLETED", "Completada")
    assert body["completed_at"] is not None
    assert [(call["task"].pk, call["actor"]) for call in recorder.calls] == [
        (task.pk, advisor_user)
    ]


def test_cancel_needs_a_reason_and_records_it(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    make_task: TaskFactory,
    django_capture_on_commit_callbacks: Any,
) -> None:
    task = make_task(make_task_application())
    assert_error(
        advisor_client.post(task_url(task, "/cancel"), {}, format="json"), 400, "VALIDATION_ERROR"
    )
    blank = advisor_client.post(task_url(task, "/cancel"), {"reason": ""}, format="json")
    assert_error(blank, 400, "VALIDATION_ERROR")

    recorder = Recorder()
    task_cancelled.connect(recorder)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = advisor_client.post(
                task_url(task, "/cancel"), {"reason": "El comprador ya los envió"}, format="json"
            )
    finally:
        task_cancelled.disconnect(recorder)

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["status"], body["cancel_reason"]) == ("CANCELLED", "El comprador ya los envió")
    assert body["cancelled_at"] is not None
    assert [call["reason"] for call in recorder.calls] == ["El comprador ya los envió"]


def test_actions_on_tasks_outside_the_scope_are_not_found(
    advisor_client: APIClient,
    other_advisor: User,
    make_task_application: AppFactory,
    make_task: TaskFactory,
) -> None:
    task = make_task(make_task_application(advisor=other_advisor), assigned_to=other_advisor)

    assert_error(advisor_client.patch(task_url(task), {}, format="json"), 404, "RESOURCE_NOT_FOUND")
    assert_error(advisor_client.post(task_url(task, "/complete")), 404, "RESOURCE_NOT_FOUND")


# --- Filtros y orden --------------------------------------------------------------------


def test_due_filters_use_the_bogota_date(
    advisor_user: User, make_task_application: AppFactory, make_task: TaskFactory
) -> None:
    application = make_task_application()
    # Hoy en Bogotá es el 10 de noviembre (de 05:00 UTC del 10 a 05:00 UTC del 11).
    make_task(application, datetime(2026, 11, 10, 4, 59, tzinfo=UTC), title="Ayer")
    make_task(application, datetime(2026, 11, 10, 5, 0, tzinfo=UTC), title="Hoy temprano")
    make_task(application, datetime(2026, 11, 11, 4, 59, tzinfo=UTC), title="Hoy tarde")
    make_task(application, datetime(2026, 11, 11, 5, 0, tzinfo=UTC), title="Mañana")
    make_task(application, None, title="Sin fecha")
    make_task(
        application,
        datetime(2026, 11, 1, tzinfo=UTC),
        title="Completada vencida",
        status=TaskStatus.COMPLETED,
        completed_at=NOW,
    )

    with freeze_time(NOW):
        client = client_for(advisor_user)
        overdue = client.get(TASKS_URL, {"due": "overdue"})
        today = client.get(TASKS_URL, {"due": "today"})
        upcoming = client.get(TASKS_URL, {"due": "upcoming"})
        every = client.get(TASKS_URL)

    assert codes(overdue) == ["Ayer"]
    assert codes(today) == ["Hoy temprano", "Hoy tarde"]
    assert codes(upcoming) == ["Mañana"]
    rows = {row["title"]: row["is_overdue"] for row in every.json()["items"]}
    assert rows == {
        "Completada vencida": False,
        "Ayer": True,
        "Hoy temprano": False,
        "Hoy tarde": False,
        "Mañana": False,
        "Sin fecha": False,
    }
    # Orden por `due_at`, las que no tienen fecha al final.
    assert codes(every) == [
        "Completada vencida",
        "Ayer",
        "Hoy temprano",
        "Hoy tarde",
        "Mañana",
        "Sin fecha",
    ]


def test_filters_by_status_parent_and_priority(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    make_task_opportunity: OppFactory,
    make_task: TaskFactory,
) -> None:
    application = make_task_application()
    opportunity = make_task_opportunity()
    make_task(application, title="Alta", priority_item=catalog_item("task_priority", "HIGH"))
    make_task(
        application,
        title="Hecha",
        status=TaskStatus.COMPLETED,
        completed_at=timezone.now(),
    )
    make_task(opportunity=opportunity, title="De la oportunidad")

    assert codes(advisor_client.get(TASKS_URL, {"status": "COMPLETED"})) == ["Hecha"]
    assert sorted(
        codes(advisor_client.get(TASKS_URL, {"application_id": str(application.pk)}))
    ) == [
        "Alta",
        "Hecha",
    ]
    assert codes(advisor_client.get(TASKS_URL, {"opportunity_id": str(opportunity.pk)})) == [
        "De la oportunidad"
    ]
    assert codes(advisor_client.get(TASKS_URL, {"priority": "HIGH"})) == ["Alta"]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"status": "DONE"}, "status"),
        ({"due": "yesterday"}, "due"),
        ({"priority": "URGENT"}, "priority"),
        ({"application_id": "no-es-uuid"}, "application_id"),
        ({"opportunity_id": "no-es-uuid"}, "opportunity_id"),
    ],
)
def test_invalid_filters_respond_400(
    advisor_client: APIClient, params: dict[str, str], field: str
) -> None:
    response = advisor_client.get(TASKS_URL, params)

    assert assert_error(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == field


def test_list_queries_do_not_grow_with_the_rows(
    advisor_client: APIClient,
    make_task_application: AppFactory,
    make_task_opportunity: OppFactory,
    make_task: TaskFactory,
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert advisor_client.get(TASKS_URL).status_code == 200
        return len(queries)

    make_task(make_task_application(), timezone.now())
    make_task(opportunity=make_task_opportunity())
    two = measure()
    for index in range(23):
        if index % 2:
            make_task(make_task_application(), timezone.now() + timedelta(days=index))
        else:
            make_task(opportunity=make_task_opportunity())

    assert measure() == two
