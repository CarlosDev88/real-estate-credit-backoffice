"""Permisos, catálogos y titular de los tipos para el expediente documental (paso 10).

- Permisos `documents.*` y `filings.prepare` para el administrador y el asesor (este,
  dentro de las solicitudes asignadas). Broker y partner solo verán el resumen.
  `filings.prepare` se siembra aquí aunque el módulo `filings` llegue en el paso 11,
  porque lo exige la generación del paquete.
- `document_rejection_reason` (público: el comprador ve la etiqueta del motivo) y
  `document_waiver_reason` (interno). Son una propuesta inicial editable.
- `holder_scope = APPLICATION` en los tipos que pertenecen a la solicitud y no a una
  persona: los del inmueble, los de legalización y la carta de aprobación externa.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"

# (código, módulo, nombre, roles)
PERMISSIONS = [
    (
        "documents.read",
        "documents",
        "Consultar el expediente documental: slots, versiones y análisis",
        [ADMIN, ADVISOR],
    ),
    ("documents.review", "documents", "Aprobar y rechazar documentos", [ADMIN, ADVISOR]),
    ("documents.waive", "documents", "Exonerar documentos", [ADMIN, ADVISOR]),
    (
        "documents.manage_requirements",
        "documents",
        "Recalcular la lista documental de una solicitud",
        [ADMIN, ADVISOR],
    ),
    ("documents.download", "documents", "Descargar documentos del expediente", [ADMIN, ADVISOR]),
    (
        "filings.prepare",
        "filings",
        "Generar y descargar el paquete documental para radicar",
        [ADMIN, ADVISOR],
    ),
]

# (código, nombre, descripción, es público, ítems)
CATALOGS = [
    (
        "document_rejection_reason",
        "Motivo de rechazo de documento",
        "Por qué el asesor rechaza una versión; el comprador ve la etiqueta.",
        True,
        [
            ("ILLEGIBLE", "Ilegible"),
            ("INCOMPLETE", "Incompleto"),
            ("OUTDATED", "Desactualizado o vencido"),
            ("WRONG_DOCUMENT", "No corresponde al documento solicitado"),
            ("DATA_MISMATCH", "Los datos no coinciden con la solicitud"),
            ("OTHER", "Otro"),
        ],
    ),
    (
        "document_waiver_reason",
        "Motivo de exoneración de documento",
        "Por qué un documento exonerable deja de exigirse en una solicitud.",
        False,
        [
            ("NOT_APPLICABLE", "No aplica al caso"),
            ("BANK_EXEMPTED", "Exonerado por el banco"),
            ("REPLACED_BY_OTHER_SUPPORT", "Cubierto por otro soporte"),
            ("OTHER", "Otro"),
        ],
    ),
]

APPLICATION_TYPES = [
    "PROPERTY_ANALYSIS_DOCUMENTS",
    "PROPERTY_OWNERSHIP_DOCUMENT",
    "REMODELING_BUDGET",
    "TITLE_STUDY_DOCUMENTS",
    "DEED_SIGNATURE_DOCUMENTS",
    "REGISTRATION_DOCUMENTS",
    "EXTERNAL_APPROVAL_LETTER",
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    DocumentType = apps.get_model("documents", "DocumentType")

    roles = {role.code: role for role in Role.objects.all()}
    for code, module, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    for code, name, description, is_public, items in CATALOGS:
        catalog, _ = Catalog.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_public": is_public,
                "is_manageable": True,
            },
        )
        for index, (item_code, label) in enumerate(items):
            CatalogItem.objects.get_or_create(
                catalog=catalog,
                code=item_code,
                defaults={"label": label, "sort_order": (index + 1) * 10},
            )

    DocumentType.objects.filter(code__in=APPLICATION_TYPES).update(holder_scope="APPLICATION")


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    DocumentType = apps.get_model("documents", "DocumentType")

    DocumentType.objects.filter(code__in=APPLICATION_TYPES).update(holder_scope="PARTICIPANT")
    codes = [code for code, *_ in CATALOGS]
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_dossier"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
