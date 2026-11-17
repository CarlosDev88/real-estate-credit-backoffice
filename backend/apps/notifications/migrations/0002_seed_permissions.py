"""Permiso `notifications.read` (paso 13): ver las notificaciones de una solicitud y sus
entregas. Para el administrador y el asesor; el alcance (asesor asignado) lo aplica la
API."""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

# (código, nombre, roles)
PERMISSIONS = [
    (
        "notifications.read",
        "Consultar las notificaciones de una solicitud y sus entregas",
        ["ADMIN", "ADVISOR"],
    ),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    roles = {role.code: role for role in Role.objects.all()}
    for code, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": "notifications", "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("identity", "0010_seed_buyer_access"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
