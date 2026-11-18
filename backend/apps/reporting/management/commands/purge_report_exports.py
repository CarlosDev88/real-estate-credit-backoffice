from typing import Any

from django.core.management.base import BaseCommand

from apps.reporting.export_jobs import purge_exports


class Command(BaseCommand):
    help = (
        "Marca EXPIRED las exportaciones de reportes vencidas (REPORTS_EXPORT_TTL_HOURS) y "
        "borra su CSV del almacenamiento; el registro se conserva. En producción se agenda "
        "con Celery beat."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        count = purge_exports()
        self.stdout.write(self.style.SUCCESS(f"Exportaciones vencidas: {count}."))
