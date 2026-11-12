from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.documents.models import FileObject, ScanStatus
from apps.documents.tasks import log_eager_failure, scan_file_object


class Command(BaseCommand):
    help = (
        "Vuelve a encolar el análisis antivirus de las versiones que siguen pendientes "
        "(reintentos agotados o un broker caído al cargar)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=15,
            help="Solo los archivos cargados hace más de estos minutos (por omisión, 15).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        cutoff = timezone.now() - timedelta(minutes=options["older_than_minutes"])
        pending = (
            FileObject.objects.filter(
                scan_status=ScanStatus.PENDING,
                created_at__lt=cutoff,
                document_file__isnull=False,
            )
            .order_by("created_at")
            .values_list("pk", flat=True)
        )
        count = 0
        for file_object_id in pending.iterator():
            result = scan_file_object.delay(str(file_object_id))
            log_eager_failure(result, f"Análisis del archivo {file_object_id}")
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Análisis reencolados: {count}."))
