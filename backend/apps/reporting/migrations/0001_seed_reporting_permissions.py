"""Permisos del dashboard y los reportes (API §22, REQUERIMIENTOS §3).

- ``dashboard.read``: administrador, asesor y broker (el broker solo recibe conteos).
- ``reports.read`` y ``reports.export``: administrador y asesor.
- ``reports.manage``: administrador (ve cualquier exportación).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("dashboard.read", "Consultar el dashboard", ["ADMIN", "ADVISOR", "INDEPENDENT_BROKER"]),
    ("reports.read", "Consultar reportes", ["ADMIN", "ADVISOR"]),
    ("reports.export", "Exportar reportes", ["ADMIN", "ADVISOR"]),
    ("reports.manage", "Administrar las exportaciones de reportes", ["ADMIN"]),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    for code, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": "reporting", "name": name}
        )
        for role in Role.objects.filter(code__in=role_codes):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, _, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
