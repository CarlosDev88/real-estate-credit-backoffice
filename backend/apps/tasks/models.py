import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

PRIORITY_CATALOG = "task_priority"


class TaskStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    COMPLETED = "COMPLETED", "Completada"
    CANCELLED = "CANCELLED", "Cancelada"


class TaskSource(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    AUTOMATIC = "AUTOMATIC", "Automática"


class Task(models.Model):
    """Tarea de seguimiento sobre una oportunidad o una solicitud (RF-20, API §15.2).

    Desvío del SQL: ``cancel_reason`` y ``cancelled_at``, para saber por qué y cuándo se
    canceló (``ck_tasks_cancellation``, como ``ck_tasks_completion``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    opportunity = models.ForeignKey(
        "crm.Opportunity",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="tasks",
    )
    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="tasks",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="tasks_assigned"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_created",
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    # Ítem del catálogo `task_priority`.
    priority_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    source = models.CharField(max_length=20, choices=TaskSource.choices, default=TaskSource.MANUAL)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        db_table = "tasks"
        ordering = [F("due_at").asc(nulls_last=True), "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(opportunity__isnull=False) | Q(application__isnull=False),
                name="ck_tasks_parent",
            ),
            models.CheckConstraint(
                condition=Q(status__in=TaskStatus.values), name="ck_tasks_status"
            ),
            models.CheckConstraint(
                condition=Q(source__in=TaskSource.values), name="ck_tasks_source"
            ),
            models.CheckConstraint(
                condition=Q(status=TaskStatus.COMPLETED, completed_at__isnull=False)
                | (~Q(status=TaskStatus.COMPLETED) & Q(completed_at__isnull=True)),
                name="ck_tasks_completion",
            ),
            models.CheckConstraint(
                condition=Q(status=TaskStatus.CANCELLED, cancelled_at__isnull=False)
                | (~Q(status=TaskStatus.CANCELLED) & Q(cancelled_at__isnull=True)),
                name="ck_tasks_cancellation",
            ),
        ]
        indexes = [
            # Bandeja del responsable y "Mi día".
            models.Index(
                fields=["assigned_to", "status", "due_at"], name="ix_tasks_assignee_status"
            ),
            models.Index(fields=["application", "status", "due_at"], name="ix_tasks_application"),
            models.Index(fields=["opportunity", "status"], name="ix_tasks_opportunity"),
        ]

    def __str__(self) -> str:
        return self.title
