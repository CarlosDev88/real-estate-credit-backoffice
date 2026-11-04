import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.catalogs.workflow import ProjectStatus


class Project(models.Model):
    """Proyecto de vivienda de una constructora.

    Nace en `DRAFT`; solo un proyecto `ACTIVE` puede recibir oportunidades nuevas.
    Archivar no borra las asociaciones históricas.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.RESTRICT, related_name="projects"
    )
    name = models.CharField(max_length=180)
    # Código interno de la constructora; opcional y único dentro del partner.
    code = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT
    )

    # Municipio DANE: ítem del catálogo `municipality`.
    city_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="projects"
    )
    address = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="projects_created"
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects_validated",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "projects"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["partner", "code"], name="uq_projects_partner_code"),
            # Un nombre no se repite dentro del partner mientras el proyecto siga abierto.
            models.UniqueConstraint(
                "partner",
                Lower("name"),
                condition=Q(deleted_at__isnull=True) & ~Q(status=ProjectStatus.ARCHIVED),
                name="uq_projects_partner_name_open",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ProjectStatus.values), name="ck_projects_status"
            ),
            models.CheckConstraint(
                condition=Q(validated_by__isnull=True, validated_at__isnull=True)
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="ck_projects_validation",
            ),
        ]
        indexes = [
            models.Index(fields=["partner", "status"], name="ix_projects_partner_status"),
        ]

    def __str__(self) -> str:
        return self.name
