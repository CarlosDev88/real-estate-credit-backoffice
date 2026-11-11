"""Permisos, catálogos y transiciones del módulo applications.

Permisos según la matriz de acceso (sección 8.6 de los requerimientos y API §16):
el administrador ve todo y el asesor gestiona sus solicitudes asignadas. El broker
solo consulta el resumen de las solicitudes de las oportunidades que originó; nunca
datos financieros. El usuario de constructora no crea ni consulta expedientes
(REQUERIMIENTOS §3, que manda sobre API §27.4).

Catálogos: los documentos no dan sus valores; son una propuesta inicial editable desde
la administración de catálogos, igual que en CRM.

Transiciones del flujo APPLICATION (sección 4.2 de los requerimientos), solo hasta
antes de radicar: de `FILED` en adelante las agrega el módulo de radicación (paso 11).
`READY_TO_FILE` exige la guarda `APPLICATION_READY_TO_FILE`. `WITHDRAWN` solo se
alcanza por `/withdrawals`.

Transiciones `CONVERT_*` del flujo OPPORTUNITY: crear la solicitud convierte la
oportunidad (la migración de CRM las dejó para este módulo).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"
BROKER = "INDEPENDENT_BROKER"

# (código, módulo, nombre, roles)
PERMISSIONS = [
    ("applications.read", "applications", "Consultar solicitudes", [ADMIN, ADVISOR, BROKER]),
    (
        "applications.read_summary",
        "applications",
        "Consultar el resumen de solicitudes",
        [ADMIN, ADVISOR, BROKER],
    ),
    (
        "applications.read_history",
        "applications",
        "Consultar el historial de estados de solicitudes",
        [ADMIN, ADVISOR],
    ),
    ("applications.create", "applications", "Crear solicitudes", [ADMIN, ADVISOR]),
    ("applications.update", "applications", "Editar solicitudes", [ADMIN, ADVISOR]),
    (
        "applications.transition",
        "applications",
        "Cambiar el estado de solicitudes",
        [ADMIN, ADVISOR],
    ),
    ("applications.assign", "applications", "Reasignar el asesor de solicitudes", [ADMIN, ADVISOR]),
    ("applications.withdraw", "applications", "Registrar el desistimiento", [ADMIN, ADVISOR]),
]

# (código, nombre, descripción, is_public, [(código, etiqueta)])
CATALOGS = [
    (
        "contract_type",
        "Tipo de contrato",
        "Contrato laboral del participante.",
        True,
        [
            ("INDEFINITE", "Término indefinido"),
            ("FIXED_TERM", "Término fijo"),
            ("WORK_OR_LABOR", "Obra o labor"),
            ("SERVICES", "Prestación de servicios"),
        ],
    ),
    (
        "funds_origin",
        "Origen de los fondos",
        "Procedencia declarada de los recursos del participante.",
        True,
        [
            ("SALARY", "Salario"),
            ("INDEPENDENT_ACTIVITY", "Actividad independiente"),
            ("PENSION", "Pensión"),
            ("SAVINGS", "Ahorros"),
            ("OTHER", "Otro origen"),
        ],
    ),
    (
        "income_source_type",
        "Tipo de ingreso",
        "Fuentes que componen el ingreso mensual del participante.",
        True,
        [
            ("SALARY", "Salario"),
            ("INDEPENDENT_ACTIVITY", "Actividad independiente"),
            ("PENSION", "Pensión"),
            ("RENTAL", "Arriendos"),
            ("OTHER", "Otro ingreso"),
        ],
    ),
    (
        "financing_mode",
        "Modalidad de financiación",
        "Recursos propios y crédito externo no exigen radicación en la plataforma.",
        True,
        [
            ("BANK_CREDIT", "Crédito bancario"),
            ("OWN_FUNDS", "Recursos propios"),
            ("EXTERNAL_CREDIT", "Crédito externo aprobado"),
        ],
    ),
    (
        "amortization_mode",
        "Modalidad de amortización",
        "",
        True,
        [
            ("FIXED_PAYMENT", "Cuota fija"),
            ("FIXED_PRINCIPAL", "Abono constante a capital"),
        ],
    ),
    (
        "application_withdrawal_reason",
        "Motivo de desistimiento",
        "Obligatorio al registrar el desistimiento de una solicitud.",
        True,
        [
            ("BUYER_DECISION", "Decisión del comprador"),
            ("OTHER_FINANCING", "Consiguió otra financiación"),
            ("PROPERTY_CHANGED", "Cambió de inmueble o desistió de la compra"),
            ("NO_RESPONSE", "El comprador no responde"),
            ("OTHER", "Otro motivo"),
        ],
    ),
    (
        "application_transition_reason",
        "Motivo de cambio de estado",
        "Motivo opcional que acompaña un cambio de estado de la solicitud.",
        False,
        [
            ("BUYER_DATA_REQUESTED", "Se solicitaron datos al comprador"),
            ("DOCUMENTS_REQUESTED", "Se solicitaron documentos"),
            ("DOCUMENTS_RECEIVED", "Documentos recibidos"),
            ("DOCUMENTS_OBSERVED", "Documentos con observaciones"),
            ("CHECKLIST_APPROVED", "Checklist aprobado"),
            ("OWN_FUNDS_CONFIRMED", "Compra con recursos propios"),
            ("EXTERNAL_CREDIT_CONFIRMED", "Crédito aprobado por otra entidad"),
            ("CANCELLED_BY_OPERATION", "Cancelada por operación"),
            ("OTHER", "Otro motivo"),
        ],
    ),
]

PRE_FILING_STATUSES = [
    "DRAFT",
    "WAITING_BUYER_DATA",
    "WAITING_DOCUMENTS",
    "DOCUMENTS_REVIEW",
    "READY_TO_FILE",
]
# Estados no terminales: desde todos se puede desistir.
NON_TERMINAL_STATUSES = [
    *PRE_FILING_STATUSES,
    "FILED",
    "FILING_VALIDATION",
    "CREDIT_ANALYSIS",
    "BANK_OBSERVATION",
    "APPROVED",
    "LEGALIZATION",
]
READY_GUARD = "APPLICATION_READY_TO_FILE"
TRANSITION = "applications.transition"
WITHDRAW = "applications.withdraw"

# (código, origen, destino, etiqueta, permiso, guarda)
APPLICATION_TRANSITIONS = [
    (
        "REQUEST_BUYER_DATA",
        "DRAFT",
        "WAITING_BUYER_DATA",
        "Solicitar datos al comprador",
        TRANSITION,
        "",
    ),
    (
        "REQUEST_DOCUMENTS",
        "WAITING_BUYER_DATA",
        "WAITING_DOCUMENTS",
        "Solicitar documentos",
        TRANSITION,
        "",
    ),
    (
        "REQUEST_DOCUMENTS_FROM_DRAFT",
        "DRAFT",
        "WAITING_DOCUMENTS",
        "Solicitar documentos",
        TRANSITION,
        "",
    ),
    (
        "START_DOCUMENTS_REVIEW",
        "WAITING_DOCUMENTS",
        "DOCUMENTS_REVIEW",
        "Iniciar revisión documental",
        TRANSITION,
        "",
    ),
    (
        "RETURN_TO_DOCUMENTS",
        "DOCUMENTS_REVIEW",
        "WAITING_DOCUMENTS",
        "Devolver a documentos",
        TRANSITION,
        "",
    ),
    (
        "MARK_READY_TO_FILE",
        "DOCUMENTS_REVIEW",
        "READY_TO_FILE",
        "Marcar lista para radicar",
        TRANSITION,
        READY_GUARD,
    ),
    (
        "REOPEN_REVIEW",
        "READY_TO_FILE",
        "DOCUMENTS_REVIEW",
        "Reabrir revisión documental",
        TRANSITION,
        "",
    ),
    *[
        (f"CANCEL_{status}", status, "CANCELLED", "Cancelar", TRANSITION, "")
        for status in PRE_FILING_STATUSES
    ],
    *[
        (f"MARK_OWN_FUNDS_{status}", status, "OWN_FUNDS", "Recursos propios", TRANSITION, "")
        for status in PRE_FILING_STATUSES
    ],
    *[
        (
            f"MARK_EXTERNAL_CREDIT_{status}",
            status,
            "EXTERNAL_CREDIT_APPROVED",
            "Crédito externo aprobado",
            TRANSITION,
            "",
        )
        for status in PRE_FILING_STATUSES
    ],
    *[
        (f"WITHDRAW_{status}", status, "WITHDRAWN", "Registrar desistimiento", WITHDRAW, "")
        for status in NON_TERMINAL_STATUSES
    ],
]

# Estados de la oportunidad desde los que crear la solicitud la convierte.
CONVERTIBLE_OPPORTUNITY_STATUSES = ["ASSIGNED", "CONTACTED", "IN_PROGRESS"]
OPPORTUNITY_TRANSITIONS = [
    (
        f"CONVERT_{status}",
        status,
        "CONVERTED",
        "Convertir en solicitud",
        "applications.create",
        "",
    )
    for status in CONVERTIBLE_OPPORTUNITY_STATUSES
]

TRANSITION_ROLES = [ADMIN, ADVISOR]
FLOWS = [("APPLICATION", APPLICATION_TRANSITIONS), ("OPPORTUNITY", OPPORTUNITY_TRANSITIONS)]


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

    for flow_type, transitions in FLOWS:
        for code, from_status, to_status, label, permission_code, guard in transitions:
            transition, _ = WorkflowTransition.objects.get_or_create(
                flow_type=flow_type,
                code=code,
                defaults={
                    "from_status": from_status,
                    "to_status": to_status,
                    "label": label,
                    "required_permission": permissions[permission_code],
                    "guard_code": guard,
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

    for flow_type, transitions in FLOWS:
        WorkflowTransition.objects.filter(
            flow_type=flow_type, code__in=[code for code, *_ in transitions]
        ).delete()
    codes = [code for code, *_ in CATALOGS]
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        ("crm", "0002_seed_permissions_catalogs_transitions"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0008_seed_user_admin_permissions"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
