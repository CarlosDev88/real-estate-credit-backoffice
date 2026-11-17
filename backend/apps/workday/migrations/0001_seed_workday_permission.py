"""Permiso de "Mi día" (API §15.1): administrador y asesor."""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CODE = "workday.read"
ROLES = ["ADMIN", "ADVISOR"]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code=CODE, defaults={"module": "workday", "name": "Consultar Mi día"}
    )
    for role in Role.objects.filter(code__in=ROLES):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
