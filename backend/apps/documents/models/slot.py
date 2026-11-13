import uuid

from django.db import models
from django.db.models import F, Q


class SlotStatus(models.TextChoices):
    """Resumen actual del documento esperado (catálogo ``document_status``)."""

    PENDING = "PENDING", "Pendiente"
    UPLOADED = "UPLOADED", "Cargado"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"
    WAIVED = "WAIVED", "Exonerado"


class PublicSlotStatus(models.TextChoices):
    """Estado del documento como lo ve el comprador, con el texto del portal."""

    TO_UPLOAD = "TO_UPLOAD", "Te falta"
    TO_FIX = "TO_FIX", "Corrígelo"
    IN_REVIEW = "IN_REVIEW", "En revisión"
    DONE = "DONE", "Listo"
    NOT_APPLICABLE = "NOT_APPLICABLE", "No aplica"


# Estado del slot → estado público. Cubre todos los `SlotStatus` (lo verifica una prueba).
PUBLIC_SLOT_STATUS: dict[str, PublicSlotStatus] = {
    SlotStatus.PENDING: PublicSlotStatus.TO_UPLOAD,
    SlotStatus.REJECTED: PublicSlotStatus.TO_FIX,
    SlotStatus.UPLOADED: PublicSlotStatus.IN_REVIEW,
    SlotStatus.APPROVED: PublicSlotStatus.DONE,
    SlotStatus.WAIVED: PublicSlotStatus.NOT_APPLICABLE,
}
# Estados públicos en los que el comprador debe actuar si el slot admite una carga.
ACTIONABLE_PUBLIC_STATUSES = (PublicSlotStatus.TO_UPLOAD, PublicSlotStatus.TO_FIX)


class ApplicationDocumentSlot(models.Model):
    """Documento concreto que espera una solicitud, copiado de un requisito publicado.

    Los valores del requisito se copian como snapshot, para que cambiar la plantilla
    mañana no altere un expediente de ayer. Cada carga es una versión nueva
    (``DocumentFile``) y ``current_file`` apunta a la vigente.

    Desvíos del DER (§8.2):

    - ``slot_index``: un requisito con ``minimum_files = n`` crea n slots, uno por
      archivo (1..n), que se cargan y revisan por separado ("Desprendible de nómina 2
      de 3").
    - ``retired_at``: el slot que deja de aplicar al recalcular la lista se retira sin
      borrarse, conserva sus versiones y vuelve si el requisito vuelve a aplicar.

    ``participant`` es nulo en los documentos de la solicitud (tipos con
    ``holder_scope = APPLICATION``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.ForeignKey(
        "applications.CreditApplication", on_delete=models.RESTRICT, related_name="document_slots"
    )
    participant = models.ForeignKey(
        "applications.ApplicationParticipant",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="document_slots",
    )
    document_type = models.ForeignKey(
        "documents.DocumentType", on_delete=models.RESTRICT, related_name="slots"
    )
    requirement = models.ForeignKey(
        "documents.DocumentRequirement",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="slots",
    )
    requirement_version = models.IntegerField(null=True, blank=True)

    # Snapshot del requisito.
    is_required = models.BooleanField()
    is_waivable = models.BooleanField()
    minimum_files = models.SmallIntegerField(default=1)
    alternative_group_code = models.CharField(max_length=50, null=True, blank=True)
    validity_days = models.SmallIntegerField(null=True, blank=True)

    slot_index = models.SmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=SlotStatus.choices, default=SlotStatus.PENDING)
    sort_order = models.IntegerField(default=0)
    # Ítem del catálogo `document_waiver_reason`.
    waiver_reason_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Versión vigente. PostgreSQL crea la FK `DEFERRABLE INITIALLY DEFERRED`, como pide
    # el esquema: la versión y el slot se escriben en la misma transacción.
    current_file = models.OneToOneField(
        "documents.DocumentFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Bloqueo posterior a la radicación (paso 11).
    locked_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "application_document_slots"
        ordering = ["sort_order", "slot_index", "created_at"]
        constraints = [
            # Desvío del DER: la "UQ funcional según tipo/participante/periodo" que el DER
            # deja abierta. Solo entre slots vigentes; un participante vacío (documento de
            # la solicitud) cuenta como un valor más.
            models.UniqueConstraint(
                fields=["application", "participant", "document_type", "slot_index"],
                condition=Q(retired_at__isnull=True),
                name="uq_document_slots_active",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(status__in=SlotStatus.values), name="ck_document_slots_status"
            ),
            models.CheckConstraint(
                condition=~Q(status=SlotStatus.WAIVED)
                | Q(is_waivable=True, waiver_reason_item__isnull=False),
                name="ck_document_slots_waiver",
            ),
            models.CheckConstraint(
                condition=Q(requirement_version__isnull=True) | Q(requirement_version__gt=0),
                name="ck_document_slots_req_version",
            ),
            models.CheckConstraint(
                condition=Q(minimum_files__gt=0), name="ck_document_slots_minimum_files"
            ),
            models.CheckConstraint(
                condition=Q(validity_days__isnull=True) | Q(validity_days__gt=0),
                name="ck_document_slots_validity_days",
            ),
            models.CheckConstraint(
                condition=Q(slot_index__gt=0, slot_index__lte=F("minimum_files")),
                name="ck_document_slots_index",
            ),
        ]
        indexes = [
            # `ix_document_slots_application_status` del esquema; Django limita los nombres
            # a 30 caracteres.
            models.Index(
                fields=["application", "status", "is_required"],
                condition=Q(retired_at__isnull=True),
                name="ix_doc_slots_app_status",
            ),
            # `ix_document_slots_pending` del esquema: obligatorios sin cumplir.
            models.Index(
                fields=["application", "sort_order"],
                include=["document_type", "participant", "status", "current_file"],
                condition=Q(is_required=True, retired_at__isnull=True)
                & ~Q(status__in=[SlotStatus.APPROVED, SlotStatus.WAIVED]),
                name="ix_doc_slots_pending",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_type_id} #{self.slot_index} ({self.status})"

    @property
    def is_retired(self) -> bool:
        return self.retired_at is not None
