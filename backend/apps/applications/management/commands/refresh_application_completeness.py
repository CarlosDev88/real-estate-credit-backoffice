from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Q

from apps.applications.models import TERMINAL_APPLICATION_STATUSES, CreditApplication
from apps.applications.services import refresh_completeness_safely


class Command(BaseCommand):
    help = (
        "Recalcula la completitud guardada que muestra el listado: las solicitudes abiertas "
        "y las que nunca se calcularon (con --all, todas). Cubre lo que cambia sin que nadie "
        "toque la solicitud: documentos que vencen, reglas o requisitos nuevos. Corre al "
        "arrancar el backend; en un entorno real se correría a diario. Siempre termina con "
        "código 0: un error en una solicitud queda en el log y el resto sigue."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help="Recalcula todas, también las cerradas que ya tienen un valor.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        applications = CreditApplication.objects.all()
        if not options["all"]:
            applications = applications.filter(
                ~Q(status__in=TERMINAL_APPLICATION_STATUSES)
                | Q(completeness_refreshed_at__isnull=True)
            )
        refreshed = failed = 0
        ids = applications.order_by("created_at").values_list("pk", flat=True)
        # Una a la vez y sin una transacción común.
        for application_id in ids.iterator(chunk_size=200):
            if refresh_completeness_safely(application_id):
                refreshed += 1
            else:
                failed += 1
        self.stdout.write(f"Completitud: {refreshed} recalculadas, {failed} con error")
