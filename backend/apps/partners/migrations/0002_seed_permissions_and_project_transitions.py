"""Permisos del módulo partners y transiciones del flujo PROJECT.

La asignación de permisos sigue la matriz de acceso (sección 8.6 de requerimientos y
sección 25 de la API). Se puede ajustar después desde la administración de roles.

Las transiciones se crean activas porque son la configuración base del flujo:
DRAFT → PENDING_REVIEW → ACTIVE → ARCHIVED, con rechazo de vuelta a DRAFT.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"
BROKER = "INDEPENDENT_BROKER"
PARTNER = "CONSTRUCTION_PARTNER"

# (código, nombre, roles)
PERMISSIONS = [
    ("partners.read", "Consultar constructoras", [ADMIN, ADVISOR, PARTNER]),
    ("partners.create", "Crear constructoras", [ADMIN]),
    ("partners.update", "Editar constructoras", [ADMIN]),
    ("partners.manage_status", "Activar y desactivar constructoras", [ADMIN]),
    ("partner_members.read", "Consultar miembros de constructoras", [ADMIN, PARTNER]),
    ("partner_members.create", "Agregar miembros a constructoras", [ADMIN]),
    ("partner_members.update", "Editar membresías", [ADMIN]),
    ("partner_members.remove", "Finalizar membresías", [ADMIN]),
    ("projects.read", "Consultar proyectos", [ADMIN, ADVISOR, PARTNER, BROKER]),
    ("projects.create", "Crear proyectos", [ADMIN, ADVISOR, PARTNER]),
    ("projects.update", "Editar proyectos", [ADMIN, ADVISOR, PARTNER]),
    ("projects.submit", "Enviar proyectos a validación", [ADMIN, ADVISOR, PARTNER]),
    ("projects.approve", "Aprobar o rechazar proyectos", [ADMIN, ADVISOR]),
    ("projects.archive", "Archivar proyectos", [ADMIN]),
]

# (código, origen, destino, etiqueta, permiso, roles)
PROJECT_TRANSITIONS = [
    (
        "SUBMIT_FOR_REVIEW",
        "DRAFT",
        "PENDING_REVIEW",
        "Enviar a validación",
        "projects.submit",
        [ADMIN, ADVISOR, PARTNER],
    ),
    ("APPROVE", "PENDING_REVIEW", "ACTIVE", "Aprobar", "projects.approve", [ADMIN, ADVISOR]),
    (
        "APPROVE_DRAFT",
        "DRAFT",
        "ACTIVE",
        "Aprobar sin enviar a validación",
        "projects.approve",
        [ADMIN, ADVISOR],
    ),
    (
        "REJECT",
        "PENDING_REVIEW",
        "DRAFT",
        "Devolver a borrador",
        "projects.approve",
        [ADMIN, ADVISOR],
    ),
    ("ARCHIVE_DRAFT", "DRAFT", "ARCHIVED", "Archivar", "projects.archive", [ADMIN]),
    ("ARCHIVE_PENDING", "PENDING_REVIEW", "ARCHIVED", "Archivar", "projects.archive", [ADMIN]),
    ("ARCHIVE_ACTIVE", "ACTIVE", "ARCHIVED", "Archivar", "projects.archive", [ADMIN]),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    WorkflowTransition = apps.get_model("catalogs", "WorkflowTransition")
    WorkflowTransitionRole = apps.get_model("catalogs", "WorkflowTransitionRole")

    roles = {role.code: role for role in Role.objects.all()}
    permissions = {}
    for code, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": code.split(".")[0], "name": name}
        )
        permissions[code] = permission
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(
                    role=roles[role_code], permission=permission
                )

    for code, from_status, to_status, label, permission_code, role_codes in PROJECT_TRANSITIONS:
        transition, _ = WorkflowTransition.objects.get_or_create(
            flow_type="PROJECT",
            code=code,
            defaults={
                "from_status": from_status,
                "to_status": to_status,
                "label": label,
                "required_permission": permissions[permission_code],
                "is_active": True,
            },
        )
        for role_code in role_codes:
            if role_code in roles:
                WorkflowTransitionRole.objects.get_or_create(
                    transition=transition, role=roles[role_code]
                )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    WorkflowTransition = apps.get_model("catalogs", "WorkflowTransition")

    WorkflowTransition.objects.filter(
        flow_type="PROJECT", code__in=[code for code, *_ in PROJECT_TRANSITIONS]
    ).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0001_initial"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
