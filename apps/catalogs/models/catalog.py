import uuid
from datetime import date

from django.db import models
from django.db.models import Q


class Catalog(models.Model):
    """Familia de tipificaciones administrables (ciudades, finalidades, motivos...)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Código estable en snake_case, por ejemplo `loan_purpose`. No se renombra.
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    # False: lo administra el backend (por ejemplo, etiquetas de estados estructurales).
    is_manageable = models.BooleanField(default=True)
    # True: visible para el comprador en el portal.
    is_public = models.BooleanField(default=False)

    # Aumenta con cada cambio del catálogo o de sus ítems; sirve para caché y ETag.
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "catalogs"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(condition=Q(version__gt=0), name="ck_catalogs_version"),
        ]

    def __str__(self) -> str:
        return self.code


class CatalogItem(models.Model):
    """Valor de una tipificación. Su `code` es estable; la `label` es editable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    catalog = models.ForeignKey(Catalog, on_delete=models.RESTRICT, related_name="items")
    code = models.CharField(max_length=50)
    label = models.CharField(max_length=180)
    description = models.TextField(blank=True)

    # Jerarquía opcional, por ejemplo departamento → municipio.
    parent_item = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="children",
    )

    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    # Datos de presentación controlados (por ejemplo, el código DANE).
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "catalog_items"
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalog", "code"], name="uq_catalog_items_catalog_code"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gte=models.F("valid_from")),
                name="ck_catalog_items_validity",
            ),
            models.CheckConstraint(
                condition=Q(parent_item__isnull=True) | ~Q(parent_item=models.F("id")),
                name="ck_catalog_items_not_own_parent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["catalog", "is_active", "sort_order"], name="ix_catalog_items_active"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.label})"

    def is_available_on(self, day: date) -> bool:
        """Activo y vigente en la fecha indicada."""
        if not self.is_active:
            return False
        if self.valid_from and day < self.valid_from:
            return False
        return not (self.valid_to and day > self.valid_to)
