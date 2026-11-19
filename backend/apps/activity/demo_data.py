"""Notas de demo (``seed_demo_data``): una nota interna en dos solicitudes del asesor."""

from apps.activity.models import ActivityLog
from apps.activity.services import add_note
from apps.applications.models import CreditApplication
from apps.identity.models import User

DEMO_NOTES = (
    "El comprador prefiere que lo llamen después de las 5 p. m.",
    "La constructora confirmó la entrega del inmueble para marzo.",
)


def seed_notes(advisor: User, applications: list[CreditApplication]) -> list[ActivityLog]:
    mine = [a for a in applications if a.assigned_advisor_id == advisor.pk]
    return [
        add_note(advisor, application, body)
        for application, body in zip(mine, DEMO_NOTES, strict=False)
    ]


# Notas del equipo (TAREA-brechas-3-demo): dos por asesor en sus solicitudes.
TEAM_NOTES = (
    "El banco pidió confirmar la dirección del empleador.",
    "El comprador quiere cerrar antes de fin de mes.",
    "Se habló con la constructora por la fecha de escrituración.",
    "Pendiente revisar el extracto de cesantías.",
)


def team_notes_exist() -> bool:
    return ActivityLog.objects.filter(message__in=TEAM_NOTES).exists()


def seed_team_notes(
    advisors: list[User], applications: list[CreditApplication]
) -> list[ActivityLog]:
    created = []
    for position, advisor in enumerate(advisors):
        mine = [a for a in applications if a.assigned_advisor_id == advisor.pk]
        bodies = TEAM_NOTES[position * 2 : position * 2 + 2]
        created += [
            add_note(advisor, application, body)
            for application, body in zip(mine, bodies, strict=False)
        ]
    return created
