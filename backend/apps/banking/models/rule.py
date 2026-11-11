import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class RuleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    ACTIVE = "ACTIVE", "Activa"
    INACTIVE = "INACTIVE", "Inactiva"


class RuleSeverity(models.TextChoices):
    WARNING = "WARNING", "Advertencia"
    BLOCKING = "BLOCKING", "Bloqueante"


class BankPolicyRule(models.Model):
    """Versión de una regla operativa de un producto. No decide la aprobación del banco.

    Una regla lógica es el par (`bank_product`, `code`); cada fila es una versión.
    Solo el borrador se edita: publicar una versión no cambia las anteriores, para
    poder saber con qué reglas se preparó un expediente antiguo. La condición es un
    JSON declarativo que interpreta ``apps.banking.rule_engine``; nunca código.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bank_product = models.ForeignKey(
        "banking.BankProduct", on_delete=models.RESTRICT, related_name="policy_rules"
    )
    # Ítem del catálogo `loan_purpose`. Vacío: aplica a todas las finalidades.
    purpose_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    code = models.CharField(max_length=80)
    version = models.IntegerField()
    severity = models.CharField(max_length=20, choices=RuleSeverity.choices)
    condition = models.JSONField()
    message = models.TextField()
    status = models.CharField(max_length=20, choices=RuleStatus.choices, default=RuleStatus.DRAFT)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="bank_policy_rules_created",
    )

    class Meta:
        db_table = "bank_policy_rules"
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank_product", "code", "version"], name="uq_bank_policy_rules_version"
            ),
            # Un solo borrador y una sola versión publicada por regla.
            models.UniqueConstraint(
                fields=["bank_product", "code"],
                condition=Q(status=RuleStatus.DRAFT),
                name="uq_bank_policy_rules_one_draft",
            ),
            models.UniqueConstraint(
                fields=["bank_product", "code"],
                condition=Q(status=RuleStatus.ACTIVE),
                name="uq_bank_policy_rules_one_active",
            ),
            models.CheckConstraint(condition=Q(version__gt=0), name="ck_bank_policy_rules_version"),
            models.CheckConstraint(
                condition=Q(severity__in=RuleSeverity.values),
                name="ck_bank_policy_rules_severity",
            ),
            models.CheckConstraint(
                condition=Q(status__in=RuleStatus.values), name="ck_bank_policy_rules_status"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="ck_bank_policy_rules_validity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["bank_product", "purpose_item", "valid_from"],
                condition=Q(status=RuleStatus.ACTIVE),
                name="ix_bank_policy_rules_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"
