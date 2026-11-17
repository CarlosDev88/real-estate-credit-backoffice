"""Catálogos, permisos y transiciones de la radicación manual (paso 11).

Catálogos:

- `filing_response_type` (lo sembró `catalogs`): se agrega `DISBURSED`. El desembolso
  se registra como una respuesta del banco, con fecha y monto.
- `filing_channel`, `filing_return_reason` y `filing_rejection_reason`: propuesta
  inicial editable, solo para usuarios internos (el comprador ve el mensaje público,
  no el motivo).

Permisos: `filings.read` para el administrador, el asesor y el broker; registrar,
corregir y responder, para el administrador y el asesor. El alcance (asesor asignado,
broker originador) lo aplica la API.

Transiciones del flujo APPLICATION de `FILED` en adelante (REQUERIMIENTOS §4.2):

- `FILE` y `BANK_*` son de sistema (``system_only``): solo las ejecutan el servicio de
  radicación y el de respuestas. `POST /status-transitions` las rechaza (`409`) y las
  acciones disponibles no las listan.
- `START_LEGALIZATION` (`APPROVED` → `LEGALIZATION`) y `MARK_READY_TO_REFILE`
  (`BANK_OBSERVATION` → `READY_TO_FILE`, con la guarda `APPLICATION_READY_TO_REFILE`)
  son manuales, por `POST /status-transitions`.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"
BROKER = "INDEPENDENT_BROKER"

# (código, nombre, roles)
PERMISSIONS = [
    ("filings.read", "Consultar radicaciones y respuestas del banco", [ADMIN, ADVISOR, BROKER]),
    ("filings.create", "Registrar la radicación manual", [ADMIN, ADVISOR]),
    ("filings.update", "Corregir la referencia o el comentario de una radicación", [ADMIN, ADVISOR]),
    ("filings.record_response", "Registrar respuestas del banco", [ADMIN, ADVISOR]),
]

RESPONSE_TYPE_CATALOG = "filing_response_type"
DISBURSED = ("DISBURSED", "Desembolsada")

# (código, nombre, descripción, [(código, etiqueta)])
CATALOGS = [
    (
        "filing_channel",
        "Canal de radicación",
        "Por dónde entregó el asesor el expediente al banco.",
        [
            ("BANK_PORTAL", "Portal del banco"),
            ("EMAIL", "Correo electrónico"),
            ("IN_PERSON", "Presencial"),
        ],
    ),
    (
        "filing_return_reason",
        "Motivo de devolución del banco",
        "Obligatorio al registrar una devolución (`RETURNED`).",
        [
            ("DOCUMENT_CORRECTION", "Corrección de documentos"),
            ("MISSING_INFORMATION", "Información incompleta"),
            ("OTHER", "Otro"),
        ],
    ),
    (
        "filing_rejection_reason",
        "Motivo de rechazo del banco",
        "Obligatorio al registrar un rechazo (`REJECTED`).",
        [
            ("CREDIT_POLICY", "Políticas del banco"),
            ("PAYMENT_CAPACITY", "Capacidad de pago insuficiente"),
            ("CREDIT_HISTORY", "Historial crediticio"),
            ("PROPERTY", "El inmueble no cumple"),
            ("OTHER", "Otro"),
        ],
    ),
]

FILE = "filings.create"
RESPOND = "filings.record_response"
TRANSITION = "applications.transition"
REFILE_GUARD = "APPLICATION_READY_TO_REFILE"

# (código, origen, destino, etiqueta, permiso, guarda, de sistema)
TRANSITIONS = [
    ("FILE", "READY_TO_FILE", "FILED", "Radicar", FILE, "", True),
    (
        "BANK_RECEIVED",
        "FILED",
        "FILING_VALIDATION",
        "Recibida por el banco",
        RESPOND,
        "",
        True,
    ),
    *[
        (f"BANK_IN_ANALYSIS_{status}", status, "CREDIT_ANALYSIS", "En análisis", RESPOND, "", True)
        for status in ("FILED", "FILING_VALIDATION")
    ],
    *[
        (
            f"BANK_RETURNED_{status}",
            status,
            "BANK_OBSERVATION",
            "Devuelta por el banco",
            RESPOND,
            "",
            True,
        )
        for status in ("FILED", "FILING_VALIDATION", "CREDIT_ANALYSIS")
    ],
    *[
        (
            f"BANK_APPROVED_{status}",
            status,
            "APPROVED",
            "Aprobada por el banco",
            RESPOND,
            "",
            True,
        )
        for status in ("FILED", "FILING_VALIDATION", "CREDIT_ANALYSIS")
    ],
    *[
        (
            f"BANK_REJECTED_{status}",
            status,
            "REJECTED",
            "Rechazada por el banco",
            RESPOND,
            "",
            True,
        )
        for status in ("FILED", "FILING_VALIDATION", "CREDIT_ANALYSIS", "BANK_OBSERVATION")
    ],
    ("BANK_DISBURSED", "LEGALIZATION", "DISBURSED", "Desembolsada", RESPOND, "", True),
    (
        "START_LEGALIZATION",
        "APPROVED",
        "LEGALIZATION",
        "Iniciar legalización",
        TRANSITION,
        "",
        False,
    ),
    (
        "MARK_READY_TO_REFILE",
        "BANK_OBSERVATION",
        "READY_TO_FILE",
        "Lista para radicar de nuevo",
        TRANSITION,
        REFILE_GUARD,
        False,
    ),
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
    for code, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": "filings", "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    response_types = Catalog.objects.get(code=RESPONSE_TYPE_CATALOG)
    last_order = max(response_types.items.values_list("sort_order", flat=True), default=0)
    item_code, label = DISBURSED
    _, created = CatalogItem.objects.get_or_create(
        catalog=response_types,
        code=item_code,
        defaults={"label": label, "sort_order": last_order + 10},
    )
    if created:
        response_types.version += 1
        response_types.save(update_fields=["version", "updated_at"])

    for code, name, description, items in CATALOGS:
        catalog, _ = Catalog.objects.get_or_create(
            code=code, defaults={"name": name, "description": description, "is_public": False}
        )
        for index, (item_code, label) in enumerate(items):
            CatalogItem.objects.get_or_create(
                catalog=catalog,
                code=item_code,
                defaults={"label": label, "sort_order": (index + 1) * 10},
            )

    permissions = {permission.code: permission for permission in Permission.objects.all()}
    for code, from_status, to_status, label, permission_code, guard, system in TRANSITIONS:
        transition, _ = WorkflowTransition.objects.get_or_create(
            flow_type="APPLICATION",
            code=code,
            defaults={
                "from_status": from_status,
                "to_status": to_status,
                "label": label,
                "required_permission": permissions[permission_code],
                "guard_code": guard,
                "is_active": True,
                "system_only": system,
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
        flow_type="APPLICATION", code__in=[code for code, *_ in TRANSITIONS]
    ).delete()
    codes = [code for code, *_ in CATALOGS]
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()
    deleted, _ = CatalogItem.objects.filter(
        catalog__code=RESPONSE_TYPE_CATALOG, code=DISBURSED[0]
    ).delete()
    if deleted:
        response_types = Catalog.objects.get(code=RESPONSE_TYPE_CATALOG)
        response_types.version += 1
        response_types.save(update_fields=["version", "updated_at"])
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("filings", "0001_initial"),
        ("applications", "0002_seed_permissions_catalogs_transitions"),
        ("catalogs", "0003_workflowtransition_system_only"),
        ("identity", "0008_seed_user_admin_permissions"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
