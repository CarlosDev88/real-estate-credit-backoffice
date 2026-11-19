"""Oportunidades de demo en todos sus estados y notas en clientes y oportunidades
(``seed_demo_data``, TAREA-brechas-3-demo).

Las convertidas ya las crean las solicitudes de la demo. Aquí van las que no llegaron a
solicitud: nuevas (del broker y del administrador, sin asesor), asignadas, contactadas,
en gestión, perdidas (con motivo) y canceladas, repartidas entre los dos asesores y con
fechas de los últimos meses. Cada cliente lleva una nota y varias oportunidades nacen con
una nota (``notes``).

Pasa por los servicios; después solo se mueven al pasado la creación de los clientes, las
oportunidades y su actividad. Marca del bloque: los clientes llevan un documento con
``OPPORTUNITY_DOCUMENT_PREFIX``; si alguno existe, no se crea nada.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.activity.models import ActivityEventType, ActivityLog
from apps.activity.services import record_activity
from apps.catalogs.models import CatalogItem
from apps.catalogs.workflow import OpportunityStatus
from apps.crm import services
from apps.crm.models import Client, Opportunity, OpportunityAssignment
from apps.identity.models import User
from apps.partners.models import Project

OPPORTUNITY_DOCUMENT_PREFIX = "9902"
S = OpportunityStatus


@dataclass(frozen=True)
class OpportunityCase:
    first_names: str
    last_names: str
    status: str
    # Quién la crea: "broker", "admin" o "advisor" (queda asignada a él).
    origin: str
    days_ago: int
    note: str = ""
    with_project: bool = False


OPPORTUNITY_CASES: tuple[OpportunityCase, ...] = (
    OpportunityCase(
        "Ricardo", "Arango Pérez", S.NEW, "broker", 2, "Llega por referido del broker."
    ),
    OpportunityCase(
        "Liliana", "Bedoya Mesa", S.NEW, "broker", 5, "Pregunta por Torres del Parque.", True
    ),
    OpportunityCase("Fernando", "Castro Gil", S.NEW, "admin", 1),
    OpportunityCase("Patricia", "Duarte León", S.ASSIGNED, "advisor", 4, "Prefiere WhatsApp."),
    OpportunityCase("Óscar", "Escobar Ruiz", S.ASSIGNED, "advisor", 9),
    OpportunityCase(
        "Gloria", "Franco Vélez", S.CONTACTED, "advisor", 12, "Ya envió la cédula por correo."
    ),
    OpportunityCase("Hugo", "Gaviria Mora", S.CONTACTED, "broker", 20),
    OpportunityCase(
        "Inés", "Hoyos Lara", S.IN_PROGRESS, "advisor", 25, "Simulación enviada.", True
    ),
    OpportunityCase("Jorge", "Ibarra Soto", S.IN_PROGRESS, "broker", 33),
    OpportunityCase("Karen", "Jiménez Ríos", S.LOST, "advisor", 60, "No volvió a contestar."),
    OpportunityCase("Luis", "Klinger Paz", S.LOST, "broker", 95),
    OpportunityCase("Mónica", "Lozada Uribe", S.CANCELLED, "advisor", 120, "Duplicada."),
    OpportunityCase("Nelson", "Muñoz Vega", S.CANCELLED, "admin", 150),
)
CLIENT_NOTES = (
    "Trabaja en el centro; llamar al mediodía.",
    "Tiene ahorro programado para la cuota inicial.",
    "Pidió información de subsidios de vivienda.",
)
LOST_REASONS = ("NO_RESPONSE", "OTHER_OPTION")


def opportunities_exist() -> bool:
    return Client.objects.filter(document_number__startswith=OPPORTUNITY_DOCUMENT_PREFIX).exists()


def _item(catalog_code: str, code: str) -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=catalog_code, code=code)


def _client(actor: User, case: OpportunityCase, number: int) -> Client:
    slug = case.first_names.lower().translate(str.maketrans("áéíóúñ", "aeioun"))
    return services.create_client(
        actor,
        {
            "document_type_item": _item("identity_document_type", "CC"),
            "document_number": f"{OPPORTUNITY_DOCUMENT_PREFIX}{number:06d}",
            "first_names": case.first_names,
            "last_names": case.last_names,
            "email": f"{slug}.{number}.o@demo.local",
            "phone": f"+57303555{number:04d}",
            "birth_date": date(1982 + number % 12, 1 + number % 12, 1 + number % 27),
        },
    )


def _move(opportunity: Opportunity, client: Client, days_ago: int) -> None:
    """Creación y actividad de la oportunidad y su cliente, ``days_ago`` días atrás."""
    delta = timedelta(days=days_ago)
    now = timezone.now()
    for model, pk in ((Client, client.pk), (Opportunity, opportunity.pk)):
        row = model.objects.get(pk=pk)
        model.objects.filter(pk=pk).update(
            created_at=row.created_at - delta, updated_at=min(row.updated_at - delta / 2, now)
        )
    for assignment in OpportunityAssignment.objects.filter(opportunity=opportunity):
        OpportunityAssignment.objects.filter(pk=assignment.pk).update(
            created_at=assignment.created_at - delta
        )
    rows = ActivityLog.objects.filter(Q(opportunity=opportunity) | Q(client=client))
    for log in rows.filter(application__isnull=True):
        ActivityLog.objects.filter(pk=log.pk).update(created_at=log.created_at - delta)


def seed_opportunities(
    *, advisors: list[User], admin: User, broker: User, project: Project | None
) -> list[Opportunity]:
    """Crea las oportunidades. Quien llama comprueba ``opportunities_exist``."""
    created = []
    for number, case in enumerate(OPPORTUNITY_CASES, start=1):
        advisor = advisors[number % len(advisors)]
        actor = {"broker": broker, "admin": admin, "advisor": advisor}[case.origin]
        client = _client(actor, case, number)
        opportunity = services.create_opportunity(
            actor,
            client=client,
            project=project if case.with_project else None,
            origin_item=_item("lead_origin", "BROKER" if case.origin == "broker" else "DIRECT"),
            notes=case.note,
        )
        if case.status != S.NEW and opportunity.assigned_advisor_id is None:
            opportunity = services.assign_advisor(admin, opportunity, advisor=advisor)
        if case.status in (S.CONTACTED, S.IN_PROGRESS):
            opportunity = services.transition_opportunity(
                advisor, opportunity, to_status=S.CONTACTED
            )
        if case.status == S.IN_PROGRESS:
            opportunity = services.transition_opportunity(
                advisor, opportunity, to_status=S.IN_PROGRESS
            )
        if case.status == S.LOST:
            opportunity = services.transition_opportunity(
                advisor,
                opportunity,
                to_status=S.LOST,
                lost_reason=_item("opportunity_lost_reason", LOST_REASONS[number % 2]),
            )
        if case.status == S.CANCELLED:
            opportunity = services.transition_opportunity(
                advisor, opportunity, to_status=S.CANCELLED, comment="Cancelada en la demo."
            )
        if number <= len(CLIENT_NOTES):
            record_activity(
                event_type=ActivityEventType.NOTE_ADDED,
                title=f"Nota de {actor.get_full_name()}",
                message=CLIENT_NOTES[number - 1],
                client=client,
                actor=actor,
            )
        _move(opportunity, client, case.days_ago)
        created.append(opportunity)
    return created
