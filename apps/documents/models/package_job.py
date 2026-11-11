import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class PackageJobStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    RUNNING = "RUNNING", "En proceso"
    COMPLETED = "COMPLETED", "Terminado"
    FAILED = "FAILED", "Fallido"
    EXPIRED = "EXPIRED", "Vencido"


class DocumentPackageJob(models.Model):
    """Trabajo asíncrono que arma el ZIP del expediente para radicar.

    El contenido se fija al pedir el paquete: ``manifest`` guarda desde ese momento las
    versiones incluidas (ids y SHA-256) y la huella documental, y el worker empaqueta
    exactamente esa lista. ``application_version`` es la versión de la solicitud en ese
    momento, solo informativa: los documentos no cambian esa versión.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        related_name="document_package_jobs",
    )
    requested_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="document_package_jobs"
    )
    application_version = models.IntegerField()
    status = models.CharField(
        max_length=20, choices=PackageJobStatus.choices, default=PackageJobStatus.PENDING
    )
    # El ZIP no pasa por el antivirus (decisión 41): se arma con versiones `CLEAN` cuyo
    # SHA-256 se verifica al empaquetar, y su `file_object` se guarda `CLEAN`, con
    # `scanned_at` al terminar. Un `file_object` que es el resultado de un trabajo es, por
    # eso, un ZIP marcado limpio al empaquetar, no por un análisis.
    output_file_object = models.OneToOneField(
        "documents.FileObject",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="package_job",
    )
    manifest = models.JSONField(null=True, blank=True)
    # Código de fallo seguro, sin detalles internos.
    error_code = models.CharField(max_length=80, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document_package_jobs"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(application_version__gt=0),
                name="ck_document_package_jobs_version",
            ),
            models.CheckConstraint(
                condition=Q(status__in=PackageJobStatus.values),
                name="ck_document_package_jobs_status",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(completed_at__isnull=True) | Q(started_at__isnull=False))
                    & (Q(completed_at__isnull=True) | Q(completed_at__gte=F("started_at")))
                    & (
                        Q(expires_at__isnull=True)
                        | Q(completed_at__isnull=True)
                        | Q(expires_at__gte=F("completed_at"))
                    )
                ),
                name="ck_document_package_jobs_dates",
            ),
        ]
        indexes = [
            # `ix_document_package_jobs_application` y `_queue` del esquema; Django limita
            # los nombres a 30 caracteres.
            models.Index(F("application"), F("created_at").desc(), name="ix_doc_package_jobs_app"),
            models.Index(
                fields=["status", "created_at"],
                condition=Q(status__in=[PackageJobStatus.PENDING, PackageJobStatus.RUNNING]),
                name="ix_doc_package_jobs_queue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application_id} ({self.status})"

    @property
    def effective_status(self) -> str:
        """El estado que ve la API: un ``COMPLETED`` cuya vigencia ya pasó es ``EXPIRED``
        aunque ``expire_document_packages`` todavía no lo haya persistido."""
        if (
            self.status == PackageJobStatus.COMPLETED
            and self.expires_at is not None
            and self.expires_at <= timezone.now()
        ):
            return PackageJobStatus.EXPIRED
        return self.status
