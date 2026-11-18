import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ReportType(models.TextChoices):
    """Reportes exportables en segundo plano. El MVP solo exporta solicitudes."""

    APPLICATIONS = "applications", "Solicitudes"


class ExportJobStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    RUNNING = "RUNNING", "En proceso"
    COMPLETED = "COMPLETED", "Terminada"
    FAILED = "FAILED", "Fallida"
    EXPIRED = "EXPIRED", "Vencida"


# Estados que ocupan uno de los cupos de exportaciones en curso del usuario.
ACTIVE_EXPORT_STATUSES: tuple[str, ...] = (ExportJobStatus.PENDING, ExportJobStatus.RUNNING)


class ReportExportJob(models.Model):
    """Exportación asíncrona de un reporte en CSV (MODELO_DATOS §10.7).

    ``filters`` guarda los filtros **ya validados**, con el rango efectivo
    (``ReportFilters.as_dict()``), nunca la query cruda. El worker vuelve a validarlos con
    el alcance del solicitante al momento de ejecutar. ``output_file_object`` es el CSV,
    marcado limpio por construcción (lo arma el sistema, no lo carga nadie).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    requested_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="report_export_jobs"
    )
    report_type = models.CharField(max_length=50, choices=ReportType.choices)
    filters = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=ExportJobStatus.choices, default=ExportJobStatus.PENDING
    )
    output_file_object = models.OneToOneField(
        "documents.FileObject",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="report_export_job",
    )
    row_count = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # Código de fallo seguro, sin detalles internos.
    error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        db_table = "report_export_jobs"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(report_type__in=ReportType.values),
                name="ck_report_export_jobs_type",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ExportJobStatus.values),
                name="ck_report_export_jobs_status",
            ),
            models.CheckConstraint(
                condition=Q(row_count__isnull=True) | Q(row_count__gte=0),
                name="ck_report_export_jobs_row_count",
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
                name="ck_report_export_jobs_dates",
            ),
        ]
        indexes = [
            models.Index(
                F("requested_by"), F("created_at").desc(), name="ix_report_export_jobs_user"
            ),
            models.Index(fields=["status", "created_at"], name="ix_report_export_jobs_queue"),
        ]

    def __str__(self) -> str:
        return f"{self.report_type} de {self.requested_by_id} ({self.status})"

    @property
    def effective_status(self) -> str:
        """Un ``COMPLETED`` vencido se lee ``EXPIRED`` aunque ``purge_report_exports``
        todavía no lo haya persistido."""
        if (
            self.status == ExportJobStatus.COMPLETED
            and self.expires_at is not None
            and self.expires_at <= timezone.now()
        ):
            return ExportJobStatus.EXPIRED
        return self.status
