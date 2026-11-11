import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class BankRuleEvaluation(models.Model):
    """Resultado inmutable de aplicar las reglas de un producto a una solicitud.

    ``result_snapshot`` guarda la regla, la versión exacta y el resultado de cada una,
    para no reinterpretar el pasado con reglas nuevas. ``application_version`` indica
    qué datos del expediente se evaluaron.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    application = models.ForeignKey(
        "applications.CreditApplication",
        on_delete=models.RESTRICT,
        related_name="rule_evaluations",
    )
    bank_product = models.ForeignKey(
        "banking.BankProduct", on_delete=models.RESTRICT, related_name="rule_evaluations"
    )
    application_version = models.IntegerField()
    is_eligible = models.BooleanField()
    blocking_count = models.SmallIntegerField(default=0)
    warning_count = models.SmallIntegerField(default=0)
    result_snapshot = models.JSONField()
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "bank_rule_evaluations"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(application_version__gt=0),
                name="ck_bank_rule_evaluations_version",
            ),
            models.CheckConstraint(
                condition=Q(blocking_count__gte=0), name="ck_bank_rule_evaluations_blocking"
            ),
            models.CheckConstraint(
                condition=Q(warning_count__gte=0), name="ck_bank_rule_evaluations_warning"
            ),
        ]
        indexes = [
            # `ix_bank_rule_evaluations_latest` del esquema; Django limita el nombre a 30
            # caracteres.
            models.Index(
                F("application"), F("created_at").desc(), name="ix_rule_evaluations_latest"
            ),
        ]

    def __str__(self) -> str:
        return f"Evaluación de {self.application_id} v{self.application_version}"
