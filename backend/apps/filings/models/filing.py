import uuid

from django.db import models
from django.db.models import F, Q


class FilingStatus(models.TextChoices):
    """Estado de una radicación: refleja la última respuesta del banco que cambió algo
    (``OTHER`` no lo cambia)."""

    FILED = "FILED", "Radicada"
    RECEIVED = "RECEIVED", "Recibida"
    IN_ANALYSIS = "IN_ANALYSIS", "En análisis"
    RETURNED = "RETURNED", "Devuelta"
    APPROVED = "APPROVED", "Aprobada"
    REJECTED = "REJECTED", "Rechazada"
    DISBURSED = "DISBURSED", "Desembolsada"


class Filing(models.Model):
    """Entrega manual del expediente al banco. La API no se comunica con el banco: el
    asesor registra aquí lo que entregó, por qué canal y cuándo.

    Una solicitud puede tener varias radicaciones (REQUERIMIENTOS §4.4); cada intento
    es una fila con su ``sequence_number`` (1, 2...). El paquete documental se usa en
    una sola radicación.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.ForeignKey(
        "applications.CreditApplication", on_delete=models.RESTRICT, related_name="filings"
    )
    bank_product = models.ForeignKey(
        "banking.BankProduct", on_delete=models.RESTRICT, related_name="filings"
    )
    package_job = models.OneToOneField(
        "documents.DocumentPackageJob", on_delete=models.RESTRICT, related_name="filing"
    )
    # Consecutivo dentro de la solicitud, desde 1.
    sequence_number = models.IntegerField()
    # Ítem del catálogo `filing_channel`.
    channel_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Número o código que dio el banco, si lo dio.
    external_reference = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=FilingStatus.choices, default=FilingStatus.FILED
    )
    filed_by = models.ForeignKey("identity.User", on_delete=models.RESTRICT, related_name="filings")
    filed_at = models.DateTimeField()
    # `filed_at` + `banks.filing_response_days`; nulo si el banco no tiene el dato.
    target_response_at = models.DateTimeField(null=True, blank=True)
    # Nota interna del asesor: el broker no la ve.
    comment = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "filings"
        ordering = ["application", "-sequence_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "sequence_number"],
                name="uq_filings_application_sequence",
            ),
            models.UniqueConstraint(
                fields=["bank_product", "external_reference"],
                condition=Q(external_reference__isnull=False),
                name="uq_filings_external_reference",
            ),
            models.CheckConstraint(condition=Q(sequence_number__gt=0), name="ck_filings_sequence"),
            models.CheckConstraint(
                condition=Q(status__in=FilingStatus.values), name="ck_filings_status"
            ),
            models.CheckConstraint(
                condition=Q(target_response_at__isnull=True)
                | Q(target_response_at__gte=F("filed_at")),
                name="ck_filings_target",
            ),
        ]
        indexes = [
            models.Index(
                F("application"), F("sequence_number").desc(), name="ix_filings_application"
            ),
            models.Index(
                fields=["status", "target_response_at"], name="ix_filings_pending_response"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application_id} #{self.sequence_number} ({self.status})"


class FilingDocumentSnapshot(models.Model):
    """Versión exacta de un documento que se entregó en la radicación. Se copia del
    manifiesto del paquete y no cambia nunca."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    filing = models.ForeignKey(Filing, on_delete=models.RESTRICT, related_name="document_snapshots")
    document_file = models.ForeignKey(
        "documents.DocumentFile", on_delete=models.RESTRICT, related_name="filing_snapshots"
    )
    file_object = models.ForeignKey(
        "documents.FileObject", on_delete=models.RESTRICT, related_name="+"
    )
    sha256 = models.CharField(max_length=64)
    document_type_code = models.CharField(max_length=80)

    class Meta:
        db_table = "filing_document_snapshots"
        ordering = ["filing", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["filing", "document_file"], name="uq_filing_document_snapshots_file"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.filing_id}: {self.document_type_code}"
