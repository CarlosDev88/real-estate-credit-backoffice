import uuid

from django.db import models
from django.db.models import Q


class ScanStatus(models.TextChoices):
    """Resultado de la validación técnica y antivirus del archivo (DER §8.1)."""

    PENDING = "PENDING", "Pendiente de análisis"
    CLEAN = "CLEAN", "Limpio"
    INFECTED = "INFECTED", "Infectado"
    INVALID = "INVALID", "Inválido"


class FileObject(models.Model):
    """Registro técnico de un archivo privado: documento, paquete o, más adelante,
    evidencia o exportación.

    La información física vive una sola vez; las tablas de negocio dicen para qué se
    usa. ``object_key`` es interno y nunca sale en una respuesta ni en un log; la
    descarga usa una URL prefirmada de corta duración, que no se guarda.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    storage_provider = models.CharField(max_length=30)
    bucket_name = models.CharField(max_length=100)
    object_key = models.CharField(max_length=500)
    # Nombre original, ya saneado (sin ruta ni caracteres de control).
    original_filename = models.CharField(max_length=255)
    # MIME real, detectado por la firma de bytes; no el que declara el navegador.
    detected_mime_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(
        max_length=30, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    scanned_at = models.DateTimeField(null=True, blank=True)
    encryption_key_version = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "file_objects"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_name", "object_key"], name="uq_file_objects_storage_key"
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=0), name="ck_file_objects_size_bytes"
            ),
            models.CheckConstraint(
                condition=Q(scan_status__in=ScanStatus.values),
                name="ck_file_objects_scan_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(scan_status=ScanStatus.PENDING, scanned_at__isnull=True)
                    | (~Q(scan_status=ScanStatus.PENDING) & Q(scanned_at__isnull=False))
                ),
                name="ck_file_objects_scan_date",
            ),
        ]
        indexes = [
            # Cola del worker de análisis.
            models.Index(
                fields=["scan_status", "created_at"],
                condition=Q(scan_status=ScanStatus.PENDING),
                name="ix_file_objects_scan_queue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.scan_status})"

    @property
    def is_clean(self) -> bool:
        return self.scan_status == ScanStatus.CLEAN
