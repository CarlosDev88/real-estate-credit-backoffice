"""Registro de actividad (API §21.1). ``record_activity`` es la única forma de crear una
fila; la llaman los suscriptores de ``apps.activity.receivers`` y las notas. Los
servicios de otras apps no importan este módulo: emiten señales."""

from typing import Any

from django.db.models import QuerySet

from apps.activity.models import ActivityEventType, ActivityLog, ActivityVisibility
from apps.activity.texts import clip
from apps.applications.models import CreditApplication
from apps.crm.models import Client, Opportunity
from apps.identity.models import BuyerSession, User

Actor = User | BuyerSession | None


def record_activity(
    *,
    event_type: str,
    title: str,
    application: CreditApplication | None = None,
    opportunity: Opportunity | None = None,
    client: Client | None = None,
    visibility: str = ActivityVisibility.INTERNAL,
    message: str = "",
    actor: Actor = None,
    metadata: dict[str, Any] | None = None,
) -> ActivityLog:
    """Crea una fila. Con una solicitud, la oportunidad y el cliente salen de ella si no
    se indican; con una oportunidad, el cliente."""
    if application is not None and opportunity is None:
        opportunity = application.opportunity
    if opportunity is not None and client is None:
        client = opportunity.client
    return ActivityLog.objects.create(
        event_type=event_type,
        visibility=visibility,
        title=clip(title),
        message=message or "",
        application=application,
        opportunity=opportunity,
        client=client,
        actor_user=actor if isinstance(actor, User) else None,
        actor_buyer_session=actor if isinstance(actor, BuyerSession) else None,
        metadata=metadata or {},
    )


def application_activity(
    application: CreditApplication, *, visibility: str, event_types: list[str] | None = None
) -> QuerySet[ActivityLog]:
    """Filas de la solicitud con esa visibilidad, de la más reciente a la más antigua."""
    rows = ActivityLog.objects.filter(application=application, visibility=visibility)
    if event_types:
        rows = rows.filter(event_type__in=event_types)
    return rows.select_related("actor_user", "actor_buyer_session").order_by("-created_at", "-id")


def application_notes(application: CreditApplication) -> QuerySet[ActivityLog]:
    return application_activity(
        application,
        visibility=ActivityVisibility.INTERNAL,
        event_types=[ActivityEventType.NOTE_ADDED],
    )


def add_note(actor: User, application: CreditApplication, body: str) -> ActivityLog:
    """Nota interna: una fila ``NOTE_ADDED`` ``INTERNAL``. Se admite también en una
    solicitud terminada."""
    return record_activity(
        event_type=ActivityEventType.NOTE_ADDED,
        title=f"Nota de {actor.get_full_name()}",
        message=body,
        application=application,
        actor=actor,
    )
