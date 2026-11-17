"""Fixtures de "Mi día": solicitudes con cliente propio, tareas y slots."""

from collections.abc import Callable
from datetime import datetime
from itertools import count
from typing import Any

import pytest

from apps.applications.models import CreditApplication, ParticipantRole
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client, Opportunity
from apps.documents.models import ApplicationDocumentSlot, DocumentType
from apps.identity.models import User
from apps.tasks.models import Task, TaskStatus
from tests.applications.buyer_access.conftest import make_link, make_session
from tests.applications.conftest import catalog_item

__all__ = ["make_link", "make_session"]

WORKDAY_URL = "/api/v1/workday/applications"
SUMMARY_URL = "/api/v1/workday/summary"

_numbers = count(1)


@pytest.fixture
def make_workday_application(
    make_client: Callable[..., Client],
    make_opportunity: Callable[..., Opportunity],
    make_application: Callable[..., CreditApplication],
    advisor_user: User,
) -> Callable[..., CreditApplication]:
    """Solicitud con su propio cliente y oportunidad, en el estado indicado."""

    def _make(
        status: str = ApplicationStatus.DRAFT,
        advisor: User | None = None,
        first_names: str = "Laura",
        **extra: Any,
    ) -> CreditApplication:
        number = next(_numbers)
        client = make_client(document_number=f"7700{number:06d}", first_names=first_names)
        opportunity = make_opportunity(client, assigned_advisor=advisor or advisor_user)
        return make_application(
            opportunity, status=status, assigned_advisor=advisor or advisor_user, **extra
        )

    return _make


@pytest.fixture
def make_task(advisor_user: User) -> Callable[..., Task]:
    def _make(application: CreditApplication, due_at: datetime | None, **extra: Any) -> Task:
        extra.setdefault("assigned_to", advisor_user)
        extra.setdefault("title", "Llamar al comprador")
        extra.setdefault("priority_item", catalog_item("task_priority", "MEDIUM"))
        extra.setdefault("status", TaskStatus.PENDING)
        return Task.objects.create(application=application, due_at=due_at, **extra)

    return _make


def add_slot(application: CreditApplication, status: str, **extra: Any) -> ApplicationDocumentSlot:
    return ApplicationDocumentSlot.objects.create(
        application=application,
        participant=application.participants.get(role=ParticipantRole.PRIMARY),
        document_type=DocumentType.objects.get(code="IDENTITY_DOCUMENT"),
        is_required=True,
        is_waivable=False,
        status=status,
        **extra,
    )
