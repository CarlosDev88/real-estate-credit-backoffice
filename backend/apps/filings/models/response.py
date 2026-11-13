import uuid

from django.db import models
from django.db.models import F, Q


class FilingResponse(models.Model):
    """Respuesta del banco a una radicación, registrada a mano por el asesor. Es
    inmutable: una corrección es otra fila que apunta a la corregida
    (``corrects_response``).

    - ``response_type_item``: ítem de `filing_response_type`.
    - ``reason_item``: de `filing_return_reason` (devolución) o `filing_rejection_reason`
      (rechazo).
    - ``public_message``: lo ve el comprador; ``internal_comment`` nunca sale hacia él.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    filing = models.ForeignKey(
        "filings.Filing", on_delete=models.RESTRICT, related_name="responses"
    )
    response_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    reason_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    received_at = models.DateTimeField()
    external_reference = models.CharField(max_length=100, null=True, blank=True)
    public_message = models.TextField(null=True, blank=True)
    internal_comment = models.TextField(null=True, blank=True)
    # Soporte de la respuesta (PDF, JPG o PNG); solo lo ven el administrador y el asesor.
    evidence_file_object = models.ForeignKey(
        "documents.FileObject",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="filing_responses",
    )
    approved_amount_cop = models.BigIntegerField(null=True, blank=True)
    approved_term_months = models.SmallIntegerField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    # Lo usará el módulo de comisiones.
    disbursed_amount_cop = models.BigIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="filing_responses"
    )
    corrects_response = models.OneToOneField(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="correction",
    )

    class Meta:
        db_table = "filing_responses"
        ordering = ["filing", "received_at", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(approved_amount_cop__isnull=True) | Q(approved_amount_cop__gte=0),
                name="ck_filing_responses_approved_amount",
            ),
            models.CheckConstraint(
                condition=Q(approved_term_months__isnull=True) | Q(approved_term_months__gt=0),
                name="ck_filing_responses_approved_term",
            ),
            models.CheckConstraint(
                condition=Q(disbursed_amount_cop__isnull=True) | Q(disbursed_amount_cop__gte=0),
                name="ck_filing_responses_disbursed_amount",
            ),
            models.CheckConstraint(
                condition=Q(corrects_response__isnull=True) | ~Q(corrects_response=F("id")),
                name="ck_filing_responses_not_self_correction",
            ),
        ]
        indexes = [
            models.Index(F("filing"), F("received_at").desc(), name="ix_filing_responses_history"),
        ]

    def __str__(self) -> str:
        return f"{self.filing_id}: {self.response_type_item_id}"


class FilingResponseObservation(models.Model):
    """Documento que el banco observó en una devolución. Queda abierta hasta que el
    asesor aprueba una versión nueva del slot (``resolved_by_file`` y ``resolved_at``)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    filing_response = models.ForeignKey(
        FilingResponse, on_delete=models.CASCADE, related_name="observations"
    )
    document_slot = models.ForeignKey(
        "documents.ApplicationDocumentSlot",
        on_delete=models.RESTRICT,
        related_name="bank_observations",
    )
    # Ítem de `document_rejection_reason`.
    reason_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Lo ve el comprador junto al documento ("Corrígelo").
    buyer_message = models.TextField()
    resolved_by_file = models.ForeignKey(
        "documents.DocumentFile",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="resolved_bank_observations",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "filing_response_observations"
        ordering = ["filing_response", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["filing_response", "document_slot"],
                name="uq_filing_response_observations_slot",
            ),
            models.CheckConstraint(
                condition=Q(resolved_by_file__isnull=True, resolved_at__isnull=True)
                | Q(resolved_by_file__isnull=False, resolved_at__isnull=False),
                name="ck_filing_response_observations_resolution",
            ),
        ]
        indexes = [
            models.Index(
                fields=["document_slot"],
                condition=Q(resolved_at__isnull=True),
                name="ix_filing_observations_open",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.filing_response_id}: {self.document_slot_id}"

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None
