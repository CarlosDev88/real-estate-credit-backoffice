import uuid

from django.conf import settings
from django.db import connection, models
from django.db.models import F, Q
from django.utils import timezone

from apps.catalogs.workflow import ApplicationStatus

# Secuencia de PostgreSQL que numera los códigos legibles `SOL-*` (migración 0001).
APPLICATION_CODE_SEQUENCE = "credit_application_code_seq"
APPLICATION_CODE_PREFIX = "SOL-"

# Estados en los que la solicitud ya terminó: no admite más cambios de estado salvo
# los que agregue un paso posterior.
TERMINAL_APPLICATION_STATUSES: tuple[str, ...] = (
    ApplicationStatus.DISBURSED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.EXTERNAL_CREDIT_APPROVED,
    ApplicationStatus.OWN_FUNDS,
    ApplicationStatus.WITHDRAWN,
    ApplicationStatus.CANCELLED,
)

# Terminales "fallidos": solo después de ellos se admite un nuevo intento sobre una
# oportunidad ya convertida.
FAILED_APPLICATION_STATUSES: tuple[str, ...] = (
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
    ApplicationStatus.CANCELLED,
)

# Estados previos a la radicación: los únicos en los que se editan los datos del
# expediente (API §16.2 y REQUERIMIENTOS §4.4).
EDITABLE_APPLICATION_STATUSES: tuple[str, ...] = (
    ApplicationStatus.DRAFT,
    ApplicationStatus.WAITING_BUYER_DATA,
    ApplicationStatus.WAITING_DOCUMENTS,
    ApplicationStatus.DOCUMENTS_REVIEW,
    ApplicationStatus.READY_TO_FILE,
)


def next_application_code() -> str:
    """Siguiente código legible, por ejemplo ``SOL-000184``. Nunca se repite."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [APPLICATION_CODE_SEQUENCE])
        (number,) = cursor.fetchone()
    return f"{APPLICATION_CODE_PREFIX}{number:06d}"


class CreditApplication(models.Model):
    """Expediente central del proceso de crédito.

    El estado y el asesor actuales viven aquí para consultar rápido; sus historiales
    están en ``application_status_history`` y ``application_assignments``, y ambas
    copias se actualizan en la misma transacción. ``version`` crece con cada cambio
    del expediente y sirve para la concurrencia optimista (``If-Match``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(max_length=30, unique=True)
    opportunity = models.ForeignKey(
        "crm.Opportunity", on_delete=models.RESTRICT, related_name="applications"
    )
    # Ítem del catálogo `loan_purpose`.
    purpose_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    bank_product = models.ForeignKey(
        "banking.BankProduct",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="applications",
    )
    assigned_advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="applications_assigned",
    )
    status = models.CharField(
        max_length=40, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT
    )
    version = models.IntegerField(default=1)
    current_stage_started_at = models.DateTimeField(default=timezone.now)
    ready_to_file_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    # Ítem del catálogo `application_withdrawal_reason`.
    withdrawal_reason_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "credit_applications"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ApplicationStatus.values),
                name="ck_credit_applications_status",
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0), name="ck_credit_applications_version"
            ),
            models.CheckConstraint(
                condition=Q(withdrawn_at__isnull=True, withdrawal_reason_item__isnull=True)
                | Q(withdrawn_at__isnull=False, withdrawal_reason_item__isnull=False),
                name="ck_credit_applications_withdrawal",
            ),
            # Idempotencia natural de la creación mientras no exista `Idempotency-Key`
            # (paso 13): una sola solicitud en curso por oportunidad.
            models.UniqueConstraint(
                fields=["opportunity"],
                condition=~Q(status__in=TERMINAL_APPLICATION_STATUSES),
                name="uq_credit_applications_open_opportunity",
            ),
        ]
        indexes = [
            # "Mi día" del asesor.
            models.Index(
                F("assigned_advisor"),
                F("status"),
                F("updated_at").desc(),
                name="ix_applications_workday",
            ),
            models.Index(
                fields=["bank_product", "status", "created_at"],
                name="ix_applications_bank_status",
            ),
            models.Index(fields=["purpose_item", "status"], name="ix_applications_purpose"),
            models.Index(
                F("opportunity"), F("created_at").desc(), name="ix_applications_opportunity"
            ),
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_APPLICATION_STATUSES

    @property
    def is_editable(self) -> bool:
        """Los datos del expediente solo se editan antes de `FILED`."""
        return self.status in EDITABLE_APPLICATION_STATUSES


class ApplicationAssignment(models.Model):
    """Historial de asesores responsables. Solo uno está vigente a la vez."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    application = models.ForeignKey(
        CreditApplication, on_delete=models.RESTRICT, related_name="assignments"
    )
    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="application_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application_assignments_made",
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "application_assignments"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(ended_at__isnull=True),
                name="uq_application_assignments_active",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("created_at")),
                name="ck_application_assignments_dates",
            ),
        ]
        indexes = [
            # `ix_application_assignments_history` del esquema; Django limita el nombre
            # a 30 caracteres.
            models.Index(
                F("application"), F("created_at").desc(), name="ix_app_assignments_history"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.advisor_id} en {self.application_id}"


class ApplicationStatusHistory(models.Model):
    """Historial inmutable de cambios de estado.

    El actor es un usuario interno (``actor_user``) o la sesión del comprador
    (``actor_buyer_session``), nunca los dos. Ninguno en el registro de un cambio que
    hizo el sistema o de un actor ya borrado.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    application = models.ForeignKey(
        CreditApplication, on_delete=models.RESTRICT, related_name="status_history"
    )
    # Vacío en el registro de creación.
    from_status = models.CharField(
        max_length=40, choices=ApplicationStatus.choices, null=True, blank=True
    )
    to_status = models.CharField(max_length=40, choices=ApplicationStatus.choices)
    transition = models.ForeignKey(
        "catalogs.WorkflowTransition",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    # Ítem de `application_transition_reason` o `application_withdrawal_reason`.
    reason_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    comment = models.TextField(blank=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    actor_buyer_session = models.ForeignKey(
        "identity.BuyerSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    application_version = models.IntegerField()

    class Meta:
        db_table = "application_status_history"
        ordering = ["-created_at"]
        verbose_name_plural = "application status history"
        constraints = [
            models.CheckConstraint(
                condition=Q(to_status__in=ApplicationStatus.values),
                name="ck_application_status_to_status",
            ),
            models.CheckConstraint(
                condition=Q(from_status__isnull=True) | Q(from_status__in=ApplicationStatus.values),
                name="ck_application_status_from_status",
            ),
            models.CheckConstraint(
                condition=Q(from_status__isnull=True) | ~Q(from_status=F("to_status")),
                name="ck_application_status_change",
            ),
            models.CheckConstraint(
                condition=Q(application_version__gt=0),
                name="ck_application_status_version",
            ),
            models.CheckConstraint(
                condition=Q(actor_user__isnull=True) | Q(actor_buyer_session__isnull=True),
                name="ck_application_status_actor",
            ),
        ]
        indexes = [
            models.Index(
                F("application"), F("created_at").desc(), name="ix_application_status_history"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application_id}: {self.from_status} → {self.to_status}"
