import uuid

from django.db import models
from django.db.models import F, Q


class ReviewDecision(models.TextChoices):
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"


class DocumentReview(models.Model):
    """Decisión del asesor sobre una versión concreta. Es inmutable: corregir una
    decisión crea otra fila, y el estado del slot es solo el resumen actual."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    document_file = models.ForeignKey(
        "documents.DocumentFile", on_delete=models.RESTRICT, related_name="reviews"
    )
    reviewer = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="document_reviews"
    )
    decision = models.CharField(max_length=20, choices=ReviewDecision.choices)
    # Ítem del catálogo `document_rejection_reason`.
    reason_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Visible para el comprador.
    buyer_comment = models.TextField(null=True, blank=True)
    # Nota privada: nunca sale hacia el comprador.
    internal_comment = models.TextField(null=True, blank=True)

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
        ]
        indexes = [
            models.Index(
                F("document_file"), F("created_at").desc(), name="ix_document_reviews_latest"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_file_id}: {self.decision}"
