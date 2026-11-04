"""Permisos, catálogos y transiciones del módulo crm.

Permisos según la matriz de acceso: el administrador ve todo, el asesor lo asignado,
el broker sus propios prospectos y la constructora no usa estos endpoints en el MVP
(sección 14 de la API y secciones 3 y 8.6 de los requerimientos).

De los catálogos, los documentos solo definen el origen `BROKER`. Los demás valores
son una propuesta inicial y se pueden editar desde la administración de catálogos.

Transiciones del flujo OPPORTUNITY (sección 4.1 de los requerimientos):
NEW → ASSIGNED → CONTACTED → IN_PROGRESS, con salida a LOST o CANCELLED desde
cualquier estado abierto. `NEW → ASSIGNED` ocurre al asignar un asesor. La
conversión (`CONVERTED`) la agrega el módulo de solicitudes (paso 8), porque una
oportunidad se convierte al crear su solicitud.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"
BROKER = "INDEPENDENT_BROKER"

PERMISSIONS = [
    ("clients.read", "clients", "Consultar clientes", [ADMIN, ADVISOR, BROKER]),
    ("clients.create", "clients", "Crear clientes", [ADMIN, ADVISOR, BROKER]),
    ("clients.update", "clients", "Editar clientes", [ADMIN, ADVISOR, BROKER]),
    ("opportunities.read", "opportunities", "Consultar oportunidades", [ADMIN, ADVISOR, BROKER]),
    ("opportunities.create", "opportunities", "Crear oportunidades", [ADMIN, ADVISOR, BROKER]),
    ("opportunities.update", "opportunities", "Editar oportunidades", [ADMIN, ADVISOR, BROKER]),
    ("opportunities.assign", "opportunities", "Asignar asesor a oportunidades", [ADMIN, ADVISOR]),
    (
        "opportunities.transition",
        "opportunities",
        "Cambiar el estado de oportunidades",
        [ADMIN, ADVISOR],
    ),
]

# (código, nombre, descripción, is_public, [(código, etiqueta)])
CATALOGS = [
    (
        "lead_origin",
        "Origen comercial",
        "Canal por el que llegó el cliente o la oportunidad.",
        False,
        [
            ("BROKER", "Broker independiente"),
            ("PARTNER_PROJECT", "Proyecto de constructora"),
            ("DIRECT", "Contacto directo"),
            ("REFERRAL", "Referido"),
        ],
    ),
    (
        "address_type",
        "Tipo de dirección",
        "",
        True,
        [
            ("RESIDENCE", "Residencia"),
            ("WORK", "Trabajo"),
            ("CORRESPONDENCE", "Correspondencia"),
        ],
    ),
    (
        "opportunity_lost_reason",
        "Motivo de pérdida de oportunidad",
        "Obligatorio al marcar una oportunidad como perdida.",
        False,
        [
            ("NO_RESPONSE", "No responde"),
            ("NOT_INTERESTED", "Ya no está interesado"),
            ("NOT_ELIGIBLE", "No cumple los requisitos"),
            ("OTHER_OPTION", "Eligió otra opción"),
            ("OTHER", "Otro motivo"),
        ],
    ),
]

OPEN_STATUSES = ["NEW", "ASSIGNED", "CONTACTED", "IN_PROGRESS"]

# (código, origen, destino, etiqueta, permiso)
TRANSITIONS = [
    ("ASSIGN", "NEW", "ASSIGNED", "Asignar asesor", "opportunities.assign"),
    ("MARK_CONTACTED", "ASSIGNED", "CONTACTED", "Marcar como contactada", "opportunities.transition"),
    ("START_PROGRESS", "CONTACTED", "IN_PROGRESS", "Iniciar gestión", "opportunities.transition"),
    *[
        (f"MARK_LOST_{status}", status, "LOST", "Marcar como perdida", "opportunities.transition")
        for status in OPEN_STATUSES
    ],
    *[
        (f"CANCEL_{status}", status, "CANCELLED", "Cancelar", "opportunities.transition")
        for status in OPEN_STATUSES
    ],
]
TRANSITION_ROLES = [ADMIN, ADVISOR]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    WorkflowTransition = apps.get_model("catalogs", "WorkflowTransition")
    WorkflowTransitionRole = apps.get_model("catalogs", "WorkflowTransitionRole")

    roles = {role.code: role for role in Role.objects.all()}
    permissions = {}
    for code, module, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        permissions[code] = permission
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(
                    role=roles[role_code], permission=permission
                )

    for code, name, description, is_public, items in CATALOGS:
        catalog, _ = Catalog.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description, "is_public": is_public},
        )
        for index, (item_code, label) in enumerate(items):
            CatalogItem.objects.get_or_create(
                catalog=catalog,
                code=item_code,
                defaults={"label": label, "sort_order": (index + 1) * 10},
            )

    for code, from_status, to_status, label, permission_code in TRANSITIONS:
        transition, _ = WorkflowTransition.objects.get_or_create(
            flow_type="OPPORTUNITY",
            code=code,
            defaults={
                "from_status": from_status,
                "to_status": to_status,
                "label": label,
                "required_permission": permissions[permission_code],
                "is_active": True,
            },
        )
        for role_code in TRANSITION_ROLES:
            if role_code in roles:
                WorkflowTransitionRole.objects.get_or_create(
                    transition=transition, role=roles[role_code]
                )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    WorkflowTransition = apps.get_model("catalogs", "WorkflowTransition")

    WorkflowTransition.objects.filter(
        flow_type="OPPORTUNITY", code__in=[code for code, *_ in TRANSITIONS]
    ).delete()
    codes = [code for code, *_ in CATALOGS]
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0001_initial"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0008_seed_user_admin_permissions"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
