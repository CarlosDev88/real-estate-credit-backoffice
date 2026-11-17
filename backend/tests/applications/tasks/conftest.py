"""Fixtures de las tareas: solicitudes y oportunidades con cliente propio, y tareas."""

from collections.abc import Callable
from datetime import datetime
from itertools import count
from typing import Any

import pytest

from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.identity.models import User
from apps.tasks.models import Task, TaskStatus
from tests.applications.conftest import catalog_item

TASKS_URL = "/api/v1/tasks"

_numbers = count(1)


def task_url(task: Task | str, suffix: str = "") -> str:
    task_id = task.pk if isinstance(task, Task) else task
    return f"{TASKS_URL}/{task_id}{suffix}"


@pytest.fixture
def make_task_opportunity(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    advisor_user: User,
) -> Callable[..., Opportunity]:
    """Oportunidad con su propio cliente."""

    def _make(advisor: User | None = None, **extra: Any) -> Opportunity:
        number = next(_numbers)
        client = make_client(document_number=f"8800{number:06d}", first_names="Sofía")
        return make_opportunity(client, assigned_advisor=advisor or advisor_user, **extra)

    return _make


@pytest.fixture
def make_task_application(
    make_task_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
    advisor_user: User,
) -> Callable[..., CreditApplication]:
    """Solicitud con su propio cliente y oportunidad, en el estado indicado."""

    def _make(
        status: str = ApplicationStatus.DRAFT, advisor: User | None = None
    ) -> CreditApplication:
        advisor = advisor or advisor_user
        opportunity = make_task_opportunity(advisor=advisor)
        return make_application(opportunity, status=status, assigned_advisor=advisor)

    return _make


@pytest.fixture
def make_task(advisor_user: User) -> Callable[..., Task]:
    def _make(
        application: CreditApplication | None = None,
        due_at: datetime | None = None,
        **extra: Any,
    ) -> Task:
        extra.setdefault("assigned_to", advisor_user)
        extra.setdefault("title", "Llamar al comprador")
        extra.setdefault("priority_item", catalog_item("task_priority", "MEDIUM"))
        extra.setdefault("status", TaskStatus.PENDING)
        return Task.objects.create(application=application, due_at=due_at, **extra)

    return _make
