from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.documents.packages import requeue_stale_packages


class Command(BaseCommand):
    help = (
        "Vuelve a encolar los paquetes para radicar que siguen pendientes o quedaron en "
        "proceso (un worker caído o un broker que no respondió al pedirlos)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=15,
            help="Solo los pedidos o tomados hace más de estos minutos (por omisión, 15).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        count = requeue_stale_packages(timedelta(minutes=options["older_than_minutes"]))
        self.stdout.write(self.style.SUCCESS(f"Paquetes reencolados: {count}."))
