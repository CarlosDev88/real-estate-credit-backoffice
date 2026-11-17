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
