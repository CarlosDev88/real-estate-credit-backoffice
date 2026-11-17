import uuid
from datetime import date

from django.db import models
from django.db.models import F, Q


class BankStatus(models.TextChoices):
    """Estados de banco y de producto (mismos valores en el esquema)."""

    ACTIVE = "ACTIVE", "Activo"
    INACTIVE = "INACTIVE", "Inactivo"


class Bank(models.Model):
    """Entidad financiera disponible para selección manual.

    No hay integración con el banco: la radicación es manual (sección 23.2 de la API).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Código interno estable, por ejemplo `BANCOLOMBIA`. No se renombra.
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=180)
    # Nombre corto opcional para listados, por ejemplo `FNA`. Vacío: se muestra `name`.
    short_name = models.CharField(max_length=30, blank=True, default="", db_default="")
    # NIT normalizado con dígito de verificación, por ejemplo `890903938-8`.
    tax_id = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=BankStatus.choices, default=BankStatus.ACTIVE)
    # Indicaciones internas para el asesor; no se muestran al comprador.
    operational_notes = models.TextField(blank=True)
    # Días que el banco suele tardar en responder una radicación. La radicación calcula
    # su `target_response_at` (`filed_at` + días); nulo: sin fecha objetivo.
    filing_response_days = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "banks"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=BankStatus.values), name="ck_banks_status"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == BankStatus.ACTIVE


class BankProduct(models.Model):
    """Producto de crédito de un banco, por ejemplo crédito hipotecario."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bank = models.ForeignKey(Bank, on_delete=models.RESTRICT, related_name="products")
    # Código dentro del banco, por ejemplo `MORTGAGE`. No se renombra.
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=180)
    # Ítem del catálogo `bank_product_type` (MORTGAGE, HOUSING_LEASING).
    product_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    status = models.CharField(max_length=20, choices=BankStatus.choices, default=BankStatus.ACTIVE)
    # Rangos operativos publicados o configurados; vacíos si el banco no los informa.
    min_amount_cop = models.BigIntegerField(null=True, blank=True)
    max_amount_cop = models.BigIntegerField(null=True, blank=True)
    min_term_months = models.SmallIntegerField(null=True, blank=True)
    max_term_months = models.SmallIntegerField(null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "bank_products"
        ordering = ["bank__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["bank", "code"], name="uq_bank_products_bank_code"),
            models.CheckConstraint(
                condition=Q(status__in=BankStatus.values), name="ck_bank_products_status"
            ),
            models.CheckConstraint(
                condition=(Q(min_amount_cop__isnull=True) | Q(min_amount_cop__gte=0))
                & (Q(max_amount_cop__isnull=True) | Q(max_amount_cop__gte=0))
                & (
                    Q(min_amount_cop__isnull=True)
                    | Q(max_amount_cop__isnull=True)
                    | Q(max_amount_cop__gte=F("min_amount_cop"))
                ),
                name="ck_bank_products_amounts",
            ),
            models.CheckConstraint(
                condition=(Q(min_term_months__isnull=True) | Q(min_term_months__gt=0))
                & (Q(max_term_months__isnull=True) | Q(max_term_months__gt=0))
                & (
                    Q(min_term_months__isnull=True)
                    | Q(max_term_months__isnull=True)
                    | Q(max_term_months__gte=F("min_term_months"))
                ),
                name="ck_bank_products_terms",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="ck_bank_products_validity",
            ),
        ]
        indexes = [
            models.Index(fields=["bank", "status"], name="ix_bank_products_bank_status"),
        ]

    def __str__(self) -> str:
        return f"{self.bank} · {self.name}"

    def is_available_on(self, day: date) -> bool:
        """Banco y producto activos, y producto vigente en la fecha indicada."""
        if self.status != BankStatus.ACTIVE or not self.bank.is_active:
            return False
        if day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


class BankProductPurpose(models.Model):
    """Finalidad admitida por un producto. Se desactiva en lugar de borrarse."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    bank_product = models.ForeignKey(BankProduct, on_delete=models.CASCADE, related_name="purposes")
    # Ítem del catálogo `loan_purpose`.
    purpose_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "bank_product_purposes"
        ordering = ["purpose_item__sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank_product", "purpose_item"],
                name="uq_bank_product_purposes_product_purpose",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_product_id} admite {self.purpose_item_id}"
