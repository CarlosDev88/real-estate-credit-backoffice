from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import DeliveryChannel, DeliveryStatus, NotificationDelivery
from apps.notifications.tasks import enqueue_email


class Command(BaseCommand):
    help = (
        "Vuelve a encolar los correos de notificaciones pendientes cuyo próximo intento ya "
        "venció (el modo local sin worker, o un broker caído al crearlos). En un entorno "
        "real corre periódicamente, por ejemplo cada minuto desde cron."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        due = (
            NotificationDelivery.objects.filter(
                channel=DeliveryChannel.EMAIL, status=DeliveryStatus.PENDING
            )
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
            .order_by("next_attempt_at")
            .values_list("pk", flat=True)
        )
        count = 0
        for delivery_id in due.iterator():
            enqueue_email(delivery_id)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Correos reencolados: {count}."))
