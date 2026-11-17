import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ActivityEventType(models.TextChoices):
    APPLICATION_CREATED = "APPLICATION_CREATED", "Solicitud creada"
    STATUS_CHANGED = "STATUS_CHANGED", "Cambio de estado"
    ADVISOR_ASSIGNED = "ADVISOR_ASSIGNED", "Asesor asignado"
    PARTICIPANT_ADDED = "PARTICIPANT_ADDED", "Participante agregado"
    PARTICIPANT_REMOVED = "PARTICIPANT_REMOVED", "Participante retirado"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED", "Documento cargado"
    DOCUMENT_REVIEWED = "DOCUMENT_REVIEWED", "Documento revisado"
    BUYER_LINK_SENT = "BUYER_LINK_SENT", "Enlace enviado al comprador"
    BUYER_SESSION_STARTED = "BUYER_SESSION_STARTED", "Ingreso del comprador"
    CONSENT_RECORDED = "CONSENT_RECORDED", "Consentimiento registrado"
    TASK_CREATED = "TASK_CREATED", "Tarea creada"
    TASK_COMPLETED = "TASK_COMPLETED", "Tarea completada"
    TASK_CANCELLED = "TASK_CANCELLED", "Tarea cancelada"
    NOTE_ADDED = "NOTE_ADDED", "Nota interna"
    FILING_CREATED = "FILING_CREATED", "Radicación"
    BANK_RESPONSE_RECORDED = "BANK_RESPONSE_RECORDED", "Respuesta del banco"


class ActivityVisibility(models.TextChoices):
    INTERNAL = "INTERNAL", "Interna"
    BUYER = "BUYER", "Comprador"


class ActivityLog(models.Model):
    """Línea de tiempo del caso y notas internas (API §21.1). Inmutable: solo se crea
    con ``apps.activity.services.record_activity``.

    ``created_at`` usa ``default`` en lugar de ``auto_now_add`` para que el backfill
    conserve la fecha del historial de estados.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    client = models.ForeignKey(
        "crm.Client", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    opportunity = models.ForeignKey(
        "crm.Opportunity", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    event_type = models.CharField(max_length=80, choices=ActivityEventType.choices)
    visibility = models.CharField(
        max_length=20, choices=ActivityVisibility.choices, default=ActivityVisibility.INTERNAL
    )
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True)
    actor_user = models.ForeignKey(
        "identity.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_buyer_session = models.ForeignKey(
        "identity.BuyerSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "activity_logs"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(client__isnull=False)
                | Q(opportunity__isnull=False)
                | Q(application__isnull=False),
                name="ck_activity_logs_resource",
            ),
            models.CheckConstraint(
                condition=Q(actor_user__isnull=True) | Q(actor_buyer_session__isnull=True),
                name="ck_activity_logs_actor",
            ),
            models.CheckConstraint(
                condition=Q(visibility__in=ActivityVisibility.values),
                name="ck_activity_logs_visibility",
            ),
        ]
        indexes = [
            models.Index(fields=["application", "-created_at"], name="ix_activity_application"),
            models.Index(fields=["opportunity", "-created_at"], name="ix_activity_opportunity"),
            models.Index(fields=["client", "-created_at"], name="ix_activity_client"),
        ]

    def __str__(self) -> str:
        return self.title
