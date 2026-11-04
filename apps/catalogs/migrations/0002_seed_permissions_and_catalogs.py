"""Datos semilla del módulo catalogs.

Solo incluye valores definidos en los documentos del proyecto (requerimientos,
secciones 2, 4, 4.5 y 7.1) o estándares de Colombia (códigos DANE de departamentos y
capitales, tipos de documento de identidad). Los demás catálogos (motivos, canales,
prioridades, etc.) los crea el módulo que los usa, en su propia migración.

La lista de municipios es parcial: departamentos y capitales. El listado DIVIPOLA
completo se carga después con una importación administrada.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("catalogs.read", "Consultar catálogos"),
    ("catalogs.create", "Crear catálogos y valores"),
    ("catalogs.update", "Editar, ordenar, activar y desactivar valores"),
    ("workflow.read", "Consultar transiciones de estado"),
    ("workflow.create", "Crear transiciones de estado"),
    ("workflow.update", "Editar transiciones inactivas"),
    ("workflow.publish", "Activar y desactivar transiciones"),
]

# (código DANE, nombre del departamento, (código DANE, nombre de la capital) | None)
DEPARTMENTS = [
    ("05", "Antioquia", ("05001", "Medellín")),
    ("08", "Atlántico", ("08001", "Barranquilla")),
    ("11", "Bogotá, D.C.", ("11001", "Bogotá, D.C.")),
    ("13", "Bolívar", ("13001", "Cartagena de Indias")),
    ("15", "Boyacá", ("15001", "Tunja")),
    ("17", "Caldas", ("17001", "Manizales")),
    ("18", "Caquetá", ("18001", "Florencia")),
    ("19", "Cauca", ("19001", "Popayán")),
    ("20", "Cesar", ("20001", "Valledupar")),
    ("23", "Córdoba", ("23001", "Montería")),
    ("25", "Cundinamarca", None),
    ("27", "Chocó", ("27001", "Quibdó")),
    ("41", "Huila", ("41001", "Neiva")),
    ("44", "La Guajira", ("44001", "Riohacha")),
    ("47", "Magdalena", ("47001", "Santa Marta")),
    ("50", "Meta", ("50001", "Villavicencio")),
    ("52", "Nariño", ("52001", "Pasto")),
    ("54", "Norte de Santander", ("54001", "Cúcuta")),
    ("63", "Quindío", ("63001", "Armenia")),
    ("66", "Risaralda", ("66001", "Pereira")),
    ("68", "Santander", ("68001", "Bucaramanga")),
    ("70", "Sucre", ("70001", "Sincelejo")),
    ("73", "Tolima", ("73001", "Ibagué")),
    ("76", "Valle del Cauca", ("76001", "Cali")),
    ("81", "Arauca", ("81001", "Arauca")),
    ("85", "Casanare", ("85001", "Yopal")),
    ("86", "Putumayo", ("86001", "Mocoa")),
    ("88", "Archipiélago de San Andrés, Providencia y Santa Catalina", ("88001", "San Andrés")),
    ("91", "Amazonas", ("91001", "Leticia")),
    ("94", "Guainía", ("94001", "Inírida")),
    ("95", "Guaviare", ("95001", "San José del Guaviare")),
    ("97", "Vaupés", ("97001", "Mitú")),
    ("99", "Vichada", ("99001", "Puerto Carreño")),
]

# (código, nombre, descripción, is_public, is_manageable, [(código, etiqueta, descripción)])
CATALOGS = [
    (
        "identity_document_type",
        "Tipo de documento de identidad",
        "Documentos de identificación aceptados para personas naturales.",
        True,
        True,
        [
            ("CC", "Cédula de ciudadanía", ""),
            ("CE", "Cédula de extranjería", ""),
            ("PA", "Pasaporte", ""),
            ("PPT", "Permiso por Protección Temporal", ""),
        ],
    ),
    (
        "loan_purpose",
        "Finalidad del crédito",
        "Finalidades del MVP. Compra de cartera y construcción en sitio propio están fuera.",
        True,
        True,
        [
            ("PURCHASE_NEW", "Compra de vivienda nueva", "Incluye vivienda sobre planos."),
            ("PURCHASE_USED", "Compra de vivienda usada", ""),
            ("HOME_IMPROVEMENT", "Remodelación o mejora de vivienda", ""),
        ],
    ),
    (
        "property_type",
        "Tipo de inmueble",
        "",
        True,
        True,
        [("HOUSE", "Casa", ""), ("APARTMENT", "Apartamento", "")],
    ),
    (
        "property_condition",
        "Estado del inmueble",
        "",
        True,
        True,
        [("NEW", "Nueva", ""), ("USED", "Usada", ""), ("OFF_PLAN", "Sobre planos", "")],
    ),
    (
        "bank_product_type",
        "Tipo de producto bancario",
        "",
        True,
        True,
        [("MORTGAGE", "Crédito hipotecario", ""), ("HOUSING_LEASING", "Leasing habitacional", "")],
    ),
    (
        "currency_mode",
        "Modalidad monetaria",
        "",
        True,
        True,
        [("COP", "Pesos", ""), ("UVR", "UVR", "Unidad de Valor Real.")],
    ),
    (
        "employment_profile",
        "Perfil laboral",
        "Determina los documentos de ingresos exigidos.",
        True,
        True,
        [
            ("EMPLOYEE", "Empleado", ""),
            ("INDEPENDENT", "Independiente", ""),
            ("PENSIONER", "Pensionado", ""),
        ],
    ),
    (
        "filing_response_type",
        "Tipo de respuesta bancaria",
        "Cada código dispara una regla del backend; solo se edita la etiqueta por migración.",
        False,
        False,
        [
            ("RECEIVED", "Recibida", ""),
            ("RETURNED", "Devuelta", ""),
            ("IN_ANALYSIS", "En análisis", ""),
            ("APPROVED", "Aprobada", ""),
            ("REJECTED", "Rechazada", ""),
            ("OTHER", "Otra", ""),
        ],
    ),
    (
        "opportunity_status",
        "Estado de oportunidad",
        "Etiquetas de los estados estructurales de la oportunidad.",
        False,
        False,
        [
            ("NEW", "Nueva", ""),
            ("ASSIGNED", "Asignada", ""),
            ("CONTACTED", "Contactada", ""),
            ("IN_PROGRESS", "En gestión", ""),
            ("CONVERTED", "Convertida", ""),
            ("LOST", "Perdida", ""),
            ("CANCELLED", "Cancelada", ""),
        ],
    ),
    (
        "application_status",
        "Estado de solicitud",
        "Etiquetas de los estados estructurales de la solicitud de crédito.",
        True,
        False,
        [
            ("DRAFT", "Borrador", ""),
            ("WAITING_BUYER_DATA", "Esperando datos del comprador", ""),
            ("WAITING_DOCUMENTS", "Esperando documentos", ""),
            ("DOCUMENTS_REVIEW", "Documentos en revisión", ""),
            ("READY_TO_FILE", "Lista para radicar", ""),
            ("FILED", "Radicada", ""),
            ("FILING_VALIDATION", "Validación de radicación", ""),
            ("CREDIT_ANALYSIS", "Análisis de crédito", ""),
            ("APPROVED", "Aprobada", ""),
            ("LEGALIZATION", "Legalización", ""),
            ("DISBURSED", "Desembolsada", ""),
            ("BANK_OBSERVATION", "Observación del banco", ""),
            ("REJECTED", "Rechazada", ""),
            ("EXTERNAL_CREDIT_APPROVED", "Crédito aprobado externamente", ""),
            ("OWN_FUNDS", "Recursos propios", ""),
            ("WITHDRAWN", "Desistida", ""),
            ("CANCELLED", "Cancelada", ""),
        ],
    ),
    (
        "project_status",
        "Estado de proyecto",
        "Etiquetas de los estados estructurales del proyecto inmobiliario.",
        False,
        False,
        [
            ("DRAFT", "Borrador", ""),
            ("PENDING_REVIEW", "En validación", ""),
            ("ACTIVE", "Activo", ""),
            ("ARCHIVED", "Archivado", ""),
        ],
    ),
    (
        "document_status",
        "Estado de documento",
        "Etiquetas de los estados del documento en el expediente.",
        True,
        False,
        [
            ("PENDING", "Pendiente", ""),
            ("UPLOADED", "Cargado", ""),
            ("APPROVED", "Aprobado", ""),
            ("REJECTED", "Rechazado", ""),
            ("WAIVED", "Exonerado", ""),
        ],
    ),
]


def _order(index: int) -> int:
    return (index + 1) * 10


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")

    admin = Role.objects.filter(code="ADMIN").first()
    for code, name in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": code.split(".")[0], "name": name}
        )
        if admin:
            RolePermission.objects.get_or_create(role=admin, permission=permission)

    for code, name, description, is_public, is_manageable, items in CATALOGS:
        catalog, _ = Catalog.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_public": is_public,
                "is_manageable": is_manageable,
            },
        )
        for index, (item_code, label, item_description) in enumerate(items):
            CatalogItem.objects.get_or_create(
                catalog=catalog,
                code=item_code,
                defaults={
                    "label": label,
                    "description": item_description,
                    "sort_order": _order(index),
                },
            )

    department_catalog, _ = Catalog.objects.get_or_create(
        code="department",
        defaults={
            "name": "Departamento",
            "description": "Departamentos de Colombia con su código DANE (DIVIPOLA).",
            "is_public": True,
        },
    )
    municipality_catalog, _ = Catalog.objects.get_or_create(
        code="municipality",
        defaults={
            "name": "Municipio",
            "description": (
                "Municipios de Colombia con su código DANE (DIVIPOLA). El padre de cada "
                "municipio es su departamento."
            ),
            "is_public": True,
        },
    )
    for index, (dane_code, name, capital) in enumerate(DEPARTMENTS):
        department, _ = CatalogItem.objects.get_or_create(
            catalog=department_catalog,
            code=dane_code,
            defaults={"label": name, "sort_order": _order(index)},
        )
        if capital:
            capital_code, capital_name = capital
            CatalogItem.objects.get_or_create(
                catalog=municipality_catalog,
                code=capital_code,
                defaults={
                    "label": capital_name,
                    "parent_item": department,
                    "metadata": {"is_capital": True},
                },
            )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")

    codes = [code for code, *_ in CATALOGS] + ["department", "municipality"]
    # Primero los hijos: `parent_item` usa RESTRICT.
    CatalogItem.objects.filter(catalog__code="municipality").delete()
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()
    Permission.objects.filter(code__in=[code for code, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0001_initial"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
