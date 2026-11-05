import uuid

from django.db import models
from django.db.models import F, Q


class RequirementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    ACTIVE = "ACTIVE", "Activo"
    INACTIVE = "INACTIVE", "Inactivo"


class ParticipantRole(models.TextChoices):
    """Rol del participante en la solicitud (``application_participants.role``).

    El paso 8 (solicitudes) es dueño de esa tabla y debe usar estos mismos valores.
    """

    PRIMARY = "PRIMARY", "Titular"
    CO_APPLICANT = "CO_APPLICANT", "Co-solicitante"
    SOLIDARY_DEBTOR = "SOLIDARY_DEBTOR", "Deudor solidario"


# Campos que identifican a un requisito lógico. Cada fila es una versión de ese alcance;
# si el alcance cambia, es otro requisito.
SCOPE_FIELDS: tuple[str, ...] = (
    "bank_product",
    "document_type",
    "purpose_item",
    "employment_profile_item",
    "participant_role",
    "property_condition_item",
)


class DocumentRequirement(models.Model):
    """Versión de la plantilla que decide qué documento se pide y en qué condiciones.

    Un requisito lógico es su alcance (``SCOPE_FIELDS``); cada fila es una versión.
    Un campo de alcance vacío significa "cualquiera": sin producto aplica a todos los
    productos (requisito general), sin rol a todos los participantes, etc. Solo el
    borrador se edita. Al armar el expediente (paso 10) la versión aplicada se copia
    al slot, para que cambiar la plantilla mañana no altere un expediente de ayer.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bank_product = models.ForeignKey(
        "banking.BankProduct",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="document_requirements",
    )
    document_type = models.ForeignKey(
        "documents.DocumentType", on_delete=models.RESTRICT, related_name="requirements"
    )
    # Ítem del catálogo `loan_purpose`.
    purpose_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Ítem del catálogo `employment_profile`.
    employment_profile_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    participant_role = models.CharField(
        max_length=30, choices=ParticipantRole.choices, null=True, blank=True
    )
    # Ítem del catálogo `property_condition`.
    property_condition_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    version = models.IntegerField()
    is_required = models.BooleanField(default=True)
    is_waivable = models.BooleanField(default=False)
    minimum_files = models.SmallIntegerField(default=1)
    # Requisitos del mismo alcance que comparten código forman un grupo "uno de estos".
    alternative_group_code = models.CharField(max_length=50, null=True, blank=True)
    # Vigencia del documento; vacío usa la sugerida por el tipo.
    validity_days = models.SmallIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=RequirementStatus.choices, default=RequirementStatus.DRAFT
    )
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document_requirements"
        ordering = ["sort_order", "document_type__code", "-version"]
        constraints = [
            # NULLS NOT DISTINCT: un campo de alcance vacío es un valor más del alcance.
            models.UniqueConstraint(
                fields=[*SCOPE_FIELDS, "version"],
                name="uq_document_requirements_version",
                nulls_distinct=False,
            ),
            # Un solo borrador y una sola versión publicada por alcance.
            models.UniqueConstraint(
                fields=list(SCOPE_FIELDS),
                condition=Q(status=RequirementStatus.DRAFT),
                name="uq_document_requirements_one_draft",
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                fields=list(SCOPE_FIELDS),
                condition=Q(status=RequirementStatus.ACTIVE),
                name="uq_document_requirements_one_active",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0), name="ck_document_requirements_version"
            ),
            models.CheckConstraint(
                condition=Q(minimum_files__gt=0), name="ck_document_requirements_minimum_files"
            ),
            models.CheckConstraint(
                condition=Q(validity_days__isnull=True) | Q(validity_days__gt=0),
                name="ck_document_requirements_validity_days",
            ),
            models.CheckConstraint(
                condition=Q(participant_role__isnull=True)
                | Q(participant_role__in=ParticipantRole.values),
                name="ck_document_requirements_role",
            ),
            models.CheckConstraint(
                condition=Q(status__in=RequirementStatus.values),
                name="ck_document_requirements_status",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="ck_document_requirements_validity",
            ),
        ]
        indexes = [
            # `ix_document_requirements_active` del esquema SQL; Django limita el nombre a
            # 30 caracteres.
            models.Index(
                fields=["bank_product", "purpose_item", "employment_profile_item", "valid_from"],
                condition=Q(status=RequirementStatus.ACTIVE),
                name="ix_doc_requirements_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_type_id} v{self.version}"

    @property
    def effective_validity_days(self) -> int | None:
        """Vigencia que se copiará al slot: la del requisito o la sugerida por el tipo."""
        if self.validity_days is not None:
            return self.validity_days
        return self.document_type.default_validity_days
