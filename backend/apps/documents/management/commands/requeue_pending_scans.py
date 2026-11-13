from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.documents.models import FileObject, ScanStatus
from apps.documents.tasks import log_eager_failure, scan_file_object


class Command(BaseCommand):
    help = (
        "Vuelve a encolar el análisis antivirus de las versiones y de las evidencias de "
        "respuestas del banco que siguen pendientes (reintentos agotados o un broker caído "
        "al cargar)."
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
        # Import local: `filings` depende de `documents`.
        from apps.filings.tasks import scan_filing_evidence

        pending = FileObject.objects.filter(
            scan_status=ScanStatus.PENDING, created_at__lt=cutoff
        ).order_by("created_at")
        count = 0
        for task, owner in (
            (scan_file_object, {"document_file__isnull": False}),
            (scan_filing_evidence, {"filing_responses__isnull": False}),
        ):
            ids = pending.filter(**owner).distinct().values_list("pk", flat=True)
            for file_object_id in ids.iterator():
                result = task.delay(str(file_object_id))
                log_eager_failure(result, f"Análisis del archivo {file_object_id}")
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Análisis reencolados: {count}."))
