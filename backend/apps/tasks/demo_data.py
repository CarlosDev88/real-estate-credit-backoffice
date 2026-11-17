"""Tareas de demo (``seed_demo_data``): vencidas, de hoy, próximas y una sin fecha, para
que "Mi día" y ``/tasks`` tengan qué mostrar. Pasan por el servicio, como en un uso real."""

from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.applications.models import CreditApplication
from apps.catalogs.models import CatalogItem
from apps.identity.models import User
from apps.tasks import services
from apps.tasks.models import PRIORITY_CATALOG, Task

# (título, días desde hoy o ``None`` sin fecha, hora local, prioridad)
DEMO_TASKS: tuple[tuple[str, int | None, int, str], ...] = (
    ("Llamar al comprador por los extractos", -3, 10, "HIGH"),
    ("Confirmar el valor del avalúo", -1, 16, "MEDIUM"),
    ("Revisar los documentos cargados hoy", 0, 11, "HIGH"),
    ("Enviar el enlace del portal al co-solicitante", 0, 17, "MEDIUM"),
    ("Pedir el certificado laboral actualizado", 1, 9, "MEDIUM"),
    ("Preparar el paquete para radicar", 3, 15, "HIGH"),
    ("Hacer seguimiento a la respuesta del banco", 7, 10, "LOW"),
    ("Agendar la firma de la promesa", None, 0, "LOW"),
)


def _due_at(days: int | None, hour: int) -> datetime | None:
    if days is None:
        return None
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour=hour)))


def seed_tasks(advisor: User, applications: list[CreditApplication]) -> list[Task]:
    """Las tareas de ``DEMO_TASKS`` sobre las solicitudes en curso del asesor, en orden."""
    mine = [a for a in applications if a.assigned_advisor_id == advisor.pk and not a.is_terminal]
    priorities = {
        item.code: item for item in CatalogItem.objects.filter(catalog__code=PRIORITY_CATALOG)
    }
    return [
        services.create_task(
            advisor,
            parent=services.TaskParent(application=mine[index % len(mine)]),
            title=title,
            due_at=_due_at(days, hour),
            priority=priorities[priority],
        )
        for index, (title, days, hour, priority) in enumerate(DEMO_TASKS)
    ]
