from typing import Any

from django.core.management.base import BaseCommand

from apps.documents.packages import expire_packages


class Command(BaseCommand):
    help = (
        "Marca EXPIRED los paquetes para radicar vencidos (DOCUMENT_PACKAGE_TTL_DAYS) y "
        "borra su ZIP del almacenamiento."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        count = expire_packages()
        self.stdout.write(self.style.SUCCESS(f"Paquetes vencidos: {count}."))
