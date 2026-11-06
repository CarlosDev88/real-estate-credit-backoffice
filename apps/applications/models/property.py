import uuid

from django.db import models
from django.db.models import Q


class Property(models.Model):
    """Inmueble que se compra o remodela. El MVP financia uno por solicitud.

    El proyecto es opcional: una vivienda nueva puede pertenecer a una constructora,
    mientras usada y remodelación existen sin proyecto.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.OneToOneField(
        "applications.CreditApplication", on_delete=models.CASCADE, related_name="financed_property"
    )
    project = models.ForeignKey(
        "partners.Project",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="properties",
    )
    # Ítem del catálogo `property_type`.
    property_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Ítem del catálogo `property_condition`.
    condition_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Ítem del catálogo `municipality`.
    city_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Obligatoria para vivienda usada y remodelación.
    address = models.CharField(max_length=255, blank=True)
    unit_reference = models.CharField(max_length=100, blank=True)
    estimated_value_cop = models.BigIntegerField()
    # Relevante para remodelación.
    is_owned_by_applicant = models.BooleanField(null=True, blank=True)
    ownership_notes = models.TextField(blank=True)

    class Meta:
        db_table = "properties"
        verbose_name_plural = "properties"
        constraints = [
            models.CheckConstraint(
                condition=Q(estimated_value_cop__gte=0), name="ck_properties_estimated_value"
            ),
        ]
        indexes = [
            models.Index(fields=["project", "created_at"], name="ix_properties_project"),
        ]

    def __str__(self) -> str:
        return f"Inmueble de {self.application_id}"


class FinancingPreference(models.Model):
    """Cómo espera financiarse el comprador. El producto elegido vive en la solicitud."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    application = models.OneToOneField(
        "applications.CreditApplication", on_delete=models.CASCADE, related_name="financing"
    )
    # Ítem del catálogo `financing_mode`.
    financing_mode_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    requested_amount_cop = models.BigIntegerField()
    term_months = models.SmallIntegerField(null=True, blank=True)
    # Ítem del catálogo `currency_mode` (COP/UVR).
    currency_mode_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Ítem del catálogo `amortization_mode`.
    amortization_mode_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    own_resources_cop = models.BigIntegerField(default=0)
    uses_severance_funds = models.BooleanField(default=False)
    severance_funds_cop = models.BigIntegerField(default=0)
    external_approved_amount_cop = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "financing_preferences"
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_amount_cop__gte=0),
                name="ck_financing_requested_amount",
            ),
            models.CheckConstraint(
                condition=Q(term_months__isnull=True) | Q(term_months__gt=0),
                name="ck_financing_term_months",
            ),
            models.CheckConstraint(
                condition=Q(own_resources_cop__gte=0), name="ck_financing_own_resources"
            ),
            models.CheckConstraint(
                condition=Q(severance_funds_cop__gte=0), name="ck_financing_severance_amount"
            ),
            models.CheckConstraint(
                condition=Q(external_approved_amount_cop__isnull=True)
                | Q(external_approved_amount_cop__gte=0),
                name="ck_financing_external_amount",
            ),
            models.CheckConstraint(
                condition=Q(uses_severance_funds=True) | Q(severance_funds_cop=0),
                name="ck_financing_severance",
            ),
        ]

    def __str__(self) -> str:
        return f"Financiación de {self.application_id}"
