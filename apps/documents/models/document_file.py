import uuid

from django.db import models
from django.db.models import F, Q


class DocumentFileStatus(models.TextChoices):
    """Estado de una versión cargada.

    - ``UPLOADED``: recién cargada, el análisis está pendiente.
    - ``IN_REVIEW``: el análisis dio ``CLEAN`` y espera la decisión del asesor.
    - ``APPROVED`` / ``REJECTED``: decisión del asesor. También ``REJECTED`` cuando el
      análisis da ``INFECTED`` o ``INVALID``, sin fila en ``document_reviews``.
    """

    UPLOADED = "UPLOADED", "Cargado"
    IN_REVIEW = "IN_REVIEW", "En revisión"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"


class DocumentFile(models.Model):
    """Versión cargada para un slot. Cada reemplazo es una fila nueva y la anterior
    nunca se sobrescribe. Solo el comprador carga: por eso la sesión es obligatoria."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    slot = models.ForeignKey(
        "documents.ApplicationDocumentSlot", on_delete=models.RESTRICT, related_name="files"
    )
    file_object = models.OneToOneField(
        "documents.FileObject", on_delete=models.RESTRICT, related_name="document_file"
    )
    # Consecutivo dentro del slot.
    version_number = models.IntegerField()
    uploaded_by_buyer_session = models.ForeignKey(
        "identity.BuyerSession", on_delete=models.RESTRICT, related_name="document_files"
    )
    client_filename = models.CharField(max_length=255)
    # Fecha de expedición o periodo; la da el comprador y el asesor puede corregirla.
    document_date = models.DateField(null=True, blank=True)
    # `document_date + validity_days` del slot.
    expires_at = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DocumentFileStatus.choices, default=DocumentFileStatus.UPLOADED
    )

    class Meta:
        db_table = "document_files"
        ordering = ["slot", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "version_number"], name="uq_document_files_slot_version"
            ),
            models.CheckConstraint(
                condition=Q(version_number__gt=0), name="ck_document_files_version"
            ),
            models.CheckConstraint(
                condition=Q(status__in=DocumentFileStatus.values),
                name="ck_document_files_status",
            ),
            # No está en el esquema: la vigencia se calcula desde la fecha del documento.
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(document_date__isnull=False, expires_at__gt=F("document_date")),
                name="ck_document_files_expiry",
            ),
        ]
        indexes = [
            models.Index(F("slot"), F("version_number").desc(), name="ix_document_files_versions"),
        ]

    def __str__(self) -> str:
        return f"{self.client_filename} v{self.version_number} ({self.status})"
