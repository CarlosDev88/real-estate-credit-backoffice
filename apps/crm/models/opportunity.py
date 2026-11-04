import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.catalogs.workflow import OpportunityStatus

# Estados en los que la oportunidad todavía se gestiona.
OPEN_OPPORTUNITY_STATUSES = (
    OpportunityStatus.NEW,
    OpportunityStatus.ASSIGNED,
    OpportunityStatus.CONTACTED,
    OpportunityStatus.IN_PROGRESS,
)


class Opportunity(models.Model):
    """Interés comercial de un cliente, opcionalmente por un proyecto.

    Un mismo cliente puede tener varias oportunidades (una por proyecto). El asesor
    actual se guarda aquí para consultar rápido; el historial está en
    `opportunity_assignments`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    client = models.ForeignKey(
        "crm.Client", on_delete=models.RESTRICT, related_name="opportunities"
    )
    project = models.ForeignKey(
        "partners.Project",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="opportunities",
    )
    # Quien capturó la oportunidad (broker o asesor).
    origin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities_originated",
    )
    assigned_advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities_assigned",
    )
    # Ítem del catálogo `lead_origin`.
    origin_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    status = models.CharField(
        max_length=30, choices=OpportunityStatus.choices, default=OpportunityStatus.NEW
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    # Ítem del catálogo `opportunity_lost_reason`; solo en estado LOST.
    lost_reason_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "opportunities"
        ordering = ["-created_at"]
        verbose_name_plural = "opportunities"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=OpportunityStatus.values),
                name="ck_opportunities_status",
            ),
            models.CheckConstraint(
                condition=Q(status=OpportunityStatus.LOST) | Q(lost_reason_item__isnull=True),
                name="ck_opportunities_lost_reason",
            ),
        ]
        # Django limita los nombres de índice a 30 caracteres; se abrevian respecto
        # al esquema (ix_opportunities_* → ix_opp_*).
        indexes = [
            models.Index(
                F("assigned_advisor"),
                F("status"),
                F("updated_at").desc(),
                name="ix_opp_advisor_status",
            ),
            models.Index(fields=["origin_user", "status"], name="ix_opp_origin_status"),
            models.Index(fields=["project", "status"], name="ix_opp_project_status"),
        ]

    def __str__(self) -> str:
        return f"Oportunidad {self.id}"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_OPPORTUNITY_STATUSES


class OpportunityAssignment(models.Model):
    """Historial de asesores responsables. Solo uno está vigente a la vez."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.RESTRICT, related_name="assignments"
    )
    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="opportunity_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunity_assignments_made",
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "opportunity_assignments"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["opportunity"],
                condition=Q(ended_at__isnull=True),
                name="uq_opportunity_assignments_active",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("created_at")),
                name="ck_opportunity_assignments_dates",
            ),
        ]
        indexes = [
            models.Index(
                F("opportunity"),
                F("created_at").desc(),
                name="ix_opp_assignments_history",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.advisor_id} en {self.opportunity_id}"
