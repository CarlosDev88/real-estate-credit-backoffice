"""Permisos, tipos documentales y checklist inicial de Bancolombia.

Permisos según la matriz de acceso (sección 8.6 de los requerimientos), igual que la
configuración bancaria: el administrador administra tipos y requisitos; el asesor
solo consulta. Broker y partner no consultan esta configuración (403). El comprador
conocerá formatos y tamaños en el paso 10, por los slots de su propia solicitud.

Tipos documentales: el catálogo documental inicial de la sección 7.1 de los
requerimientos (17 tipos). `INCOME_TAX_PROOF` no es un tipo sino el código del grupo
alternativo que forman `INCOME_RETENTION_CERTIFICATE` e `INCOME_TAX_RETURN`. Todos
admiten PDF, JPEG y PNG hasta 10 MB (sección 9.3). Solo son repetibles los que se
piden por periodos (nómina, extractos y pagos de pensión).

Requisitos: el checklist inicial de Bancolombia (sección 7.1) sobre su producto
`MORTGAGE`, como versión 1 `ACTIVE` vigente desde el 2026-01-01. Aplican a todas las
finalidades, condiciones del inmueble y participantes; los de ingresos dependen del
perfil laboral de cada participante. FNA y Banco de Bogotá quedan sin requisitos, y
los tipos marcados como "configurables" existen sin requisito hasta recibir el anexo
oficial del banco.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"

# (código, módulo, nombre, roles)
PERMISSIONS = [
    (
        "document_requirements.read",
        "document_requirements",
        "Consultar tipos y requisitos documentales",
        [ADMIN, ADVISOR],
    ),
    (
        "document_requirements.create",
        "document_requirements",
        "Crear tipos y requisitos documentales",
        [ADMIN],
    ),
    (
        "document_requirements.update",
        "document_requirements",
        "Editar tipos y requisitos documentales",
        [ADMIN],
    ),
    (
        "document_requirements.publish",
        "document_requirements",
        "Publicar, activar y desactivar tipos y requisitos documentales",
        [ADMIN],
    ),
]

MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"]
MAX_SIZE_BYTES = 10 * 1024 * 1024

# (código, nombre, descripción, es repetible)
DOCUMENT_TYPES = [
    (
        "IDENTITY_DOCUMENT",
        "Copia del documento de identidad",
        "Por ambas caras y legible.",
        False,
    ),
    (
        "INCOME_RETENTION_CERTIFICATE",
        "Certificado de ingresos y retenciones",
        "Del último año gravable.",
        False,
    ),
    (
        "INCOME_TAX_RETURN",
        "Declaración de renta",
        "Del último año gravable.",
        False,
    ),
    (
        "EMPLOYMENT_CERTIFICATE",
        "Certificación laboral",
        "Debe indicar salario, cargo, fecha de ingreso y tipo de contrato.",
        False,
    ),
    (
        "PAYROLL_SLIP",
        "Desprendible o comprobante de nómina",
        "Un archivo por periodo.",
        True,
    ),
    (
        "BANK_STATEMENT",
        "Extracto bancario",
        "Un archivo por mes.",
        True,
    ),
    (
        "INDEPENDENT_INCOME_SUPPORT",
        "Soporte de actividad e ingresos",
        "Contrato, certificación o soporte equivalente validado por el asesor.",
        False,
    ),
    (
        "PENSION_CERTIFICATE",
        "Certificación de pensión",
        "Expedida por la entidad pagadora de la pensión.",
        False,
    ),
    (
        "PENSION_PAYMENT_SLIP",
        "Comprobante de pago de pensión",
        "Un archivo por periodo.",
        True,
    ),
    (
        "CO_APPLICANT_INCOME_SUPPORT",
        "Soportes de ingresos del segundo solicitante",
        "Para cada solicitante adicional que aporta ingresos.",
        False,
    ),
    (
        "EXTERNAL_APPROVAL_LETTER",
        "Carta de aprobación externa",
        "Para finalizar la modalidad de crédito aprobado externamente.",
        False,
    ),
    (
        "PROPERTY_ANALYSIS_DOCUMENTS",
        "Soportes del inmueble para análisis y legalización",
        "",
        False,
    ),
    ("TITLE_STUDY_DOCUMENTS", "Documentos para estudio de títulos", "", False),
    ("DEED_SIGNATURE_DOCUMENTS", "Documentos para firma de escritura", "", False),
    ("REGISTRATION_DOCUMENTS", "Escritura registrada y soportes de registro", "", False),
    (
        "PROPERTY_OWNERSHIP_DOCUMENT",
        "Documento de propiedad o soporte equivalente",
        "",
        False,
    ),
    (
        "REMODELING_BUDGET",
        "Presupuesto, cotización o soporte técnico de la obra",
        "",
        False,
    ),
]

BANK_CODE = "BANCOLOMBIA"
PRODUCT_CODE = "MORTGAGE"
VALID_FROM = datetime(2026, 1, 1, tzinfo=ZoneInfo("America/Bogota"))
INCOME_TAX_GROUP = "INCOME_TAX_PROOF"

# Checklist de Bancolombia:
# (tipo, perfil laboral, mínimo de archivos, grupo alternativo, vigencia en días,
#  es exonerable)
BANCOLOMBIA_REQUIREMENTS = [
    ("IDENTITY_DOCUMENT", None, 1, None, None, False),
    ("INCOME_RETENTION_CERTIFICATE", None, 1, INCOME_TAX_GROUP, None, True),
    ("INCOME_TAX_RETURN", None, 1, INCOME_TAX_GROUP, None, True),
    ("EMPLOYMENT_CERTIFICATE", "EMPLOYEE", 1, None, 30, False),
    ("PAYROLL_SLIP", "EMPLOYEE", 3, None, None, False),
    ("BANK_STATEMENT", "INDEPENDENT", 3, None, None, False),
    ("INDEPENDENT_INCOME_SUPPORT", "INDEPENDENT", 1, None, None, False),
    ("PENSION_CERTIFICATE", "PENSIONER", 1, None, None, False),
    ("PENSION_PAYMENT_SLIP", "PENSIONER", 3, None, None, False),
]


def _order(index: int) -> int:
    return (index + 1) * 10


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    BankProduct = apps.get_model("banking", "BankProduct")
    DocumentType = apps.get_model("documents", "DocumentType")
    DocumentRequirement = apps.get_model("documents", "DocumentRequirement")

    roles = {role.code: role for role in Role.objects.all()}
    for code, module, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    types = {}
    for code, name, description, is_repeatable in DOCUMENT_TYPES:
        types[code], _ = DocumentType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "allowed_mime_types": MIME_TYPES,
                "max_size_bytes": MAX_SIZE_BYTES,
                "is_repeatable": is_repeatable,
            },
        )

    product = BankProduct.objects.filter(bank__code=BANK_CODE, code=PRODUCT_CODE).first()
    if product is None:
        return
    profiles = {
        item.code: item for item in CatalogItem.objects.filter(catalog__code="employment_profile")
    }
    for index, (type_code, profile, minimum_files, group, validity_days, is_waivable) in enumerate(
        BANCOLOMBIA_REQUIREMENTS
    ):
        DocumentRequirement.objects.get_or_create(
            bank_product=product,
            document_type=types[type_code],
            purpose_item=None,
            employment_profile_item=profiles[profile] if profile else None,
            participant_role=None,
            property_condition_item=None,
            version=1,
            defaults={
                "is_required": True,
                "is_waivable": is_waivable,
                "minimum_files": minimum_files,
                "alternative_group_code": group,
                "validity_days": validity_days,
                "sort_order": _order(index),
                "status": "ACTIVE",
                "valid_from": VALID_FROM,
            },
        )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    DocumentType = apps.get_model("documents", "DocumentType")
    DocumentRequirement = apps.get_model("documents", "DocumentRequirement")

    type_codes = [code for code, *_ in DOCUMENT_TYPES]
    DocumentRequirement.objects.filter(
        bank_product__bank__code=BANK_CODE,
        bank_product__code=PRODUCT_CODE,
        document_type__code__in=type_codes,
        version=1,
    ).delete()
    DocumentType.objects.filter(code__in=type_codes, requirements__isnull=True).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
        ("banking", "0002_seed_permissions_and_banks"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
