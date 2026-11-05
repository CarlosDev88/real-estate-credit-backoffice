import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q


class DocumentType(models.Model):
    """Tipo de soporte que puede pedir el sistema, por ejemplo la certificación laboral.

    Define solo las restricciones técnicas del archivo. Qué banco, finalidad o perfil
    lo exige lo dicen los requisitos (``DocumentRequirement``), que reutilizan el mismo
    tipo sin duplicar su definición.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Código estable, por ejemplo `EMPLOYMENT_CERTIFICATE`. No se renombra.
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=180)
    # Instrucción para quien carga el documento.
    description = models.TextField(blank=True)
    # Subconjunto de `apps.documents.constants.ALLOWED_MIME_TYPES`.
    allowed_mime_types = ArrayField(models.TextField())
    max_size_bytes = models.BigIntegerField()
    # Vigencia sugerida; un requisito puede fijar la suya.
    default_validity_days = models.SmallIntegerField(null=True, blank=True)
    # Admite varios archivos o periodos, por ejemplo tres desprendibles de nómina.
    is_repeatable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "document_types"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_size_bytes__gt=0), name="ck_document_types_max_size"
            ),
            models.CheckConstraint(
                condition=Q(default_validity_days__isnull=True) | Q(default_validity_days__gt=0),
                name="ck_document_types_validity_days",
            ),
            models.CheckConstraint(
                condition=Q(allowed_mime_types__len__gt=0),
                name="ck_document_types_mime_types",
            ),
        ]

    def __str__(self) -> str:
        return self.name
