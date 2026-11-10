import uuid

from django.db import models
from django.db.models import F, Q


class ReviewDecision(models.TextChoices):
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"
    WAIVED = "WAIVED", "Exonerado"
    REOPENED = "REOPENED", "Exoneración reabierta"


# Decisiones sobre una versión concreta; exonerar y reabrir son decisiones sobre el slot.
FILE_DECISIONS = (ReviewDecision.APPROVED, ReviewDecision.REJECTED)
SLOT_DECISIONS = (ReviewDecision.WAIVED, ReviewDecision.REOPENED)


class DocumentReview(models.Model):
    """Decisión del asesor sobre un slot. Es inmutable: corregir una decisión crea otra
    fila, y el estado del slot es solo el resumen actual.

    Desvío del DER (§8.2, Parte 5 del paso 10): la tabla también guarda las
    exoneraciones y sus reaperturas, para que quede quién las hizo y cuándo.

    - ``slot`` siempre; ``document_file`` es la versión revisada, obligatoria al aprobar
      o rechazar. Al exonerar o reabrir guarda la versión vigente, si la hay.
    - ``decision_batch_id`` agrupa las filas de una misma exoneración (todos los slots
      de un grupo alternativo comparten el lote) o de una misma reapertura. Las
      aprobaciones y los rechazos no llevan lote.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    slot = models.ForeignKey(
        "documents.ApplicationDocumentSlot", on_delete=models.RESTRICT, related_name="reviews"
    )
    document_file = models.ForeignKey(
        "documents.DocumentFile",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="reviews",
    )
    reviewer = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="document_reviews"
    )
    decision = models.CharField(max_length=20, choices=ReviewDecision.choices)
    # Ítem de `document_rejection_reason` (rechazo) o `document_waiver_reason`
    # (exoneración).
    reason_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Visible para el comprador.
    buyer_comment = models.TextField(null=True, blank=True)
    # Nota privada: nunca sale hacia el comprador.
    internal_comment = models.TextField(null=True, blank=True)
    decision_batch_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "document_reviews"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(decision__in=ReviewDecision.values),
                name="ck_document_reviews_decision",
            ),
            models.CheckConstraint(
                condition=~Q(decision=ReviewDecision.REJECTED)
                | Q(reason_item__isnull=False, buyer_comment__isnull=False),
                name="ck_document_reviews_rejection",
            ),
            models.CheckConstraint(
                condition=~Q(decision__in=FILE_DECISIONS)
                | Q(document_file__isnull=False, decision_batch_id__isnull=True),
                name="ck_document_reviews_file",
            ),
            models.CheckConstraint(
                condition=~Q(decision__in=SLOT_DECISIONS) | Q(decision_batch_id__isnull=False),
                name="ck_document_reviews_batch",
            ),
            models.CheckConstraint(
                condition=~Q(decision=ReviewDecision.WAIVED) | Q(reason_item__isnull=False),
                name="ck_document_reviews_waiver",
            ),
            models.CheckConstraint(
                condition=~Q(decision=ReviewDecision.REOPENED)
                | (Q(internal_comment__isnull=False) & ~Q(internal_comment="")),
                name="ck_document_reviews_reopen",
            ),
        ]
        indexes = [
            models.Index(
                F("document_file"), F("created_at").desc(), name="ix_document_reviews_latest"
            ),
            models.Index(F("slot"), F("created_at").desc(), name="ix_document_reviews_slot"),
            models.Index(
                fields=["decision_batch_id"],
                condition=Q(decision_batch_id__isnull=False),
                name="ix_document_reviews_batch",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.slot_id}: {self.decision}"
