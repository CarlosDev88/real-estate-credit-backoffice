"""Permisos de las tareas (API §15.2): administrador y asesor."""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("tasks.read", "Consultar tareas"),
    ("tasks.create", "Crear tareas"),
    ("tasks.update", "Editar tareas"),
    ("tasks.complete", "Completar tareas"),
    ("tasks.cancel", "Cancelar tareas"),
]
ROLES = ["ADMIN", "ADVISOR"]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    roles = list(Role.objects.filter(code__in=ROLES))
    for code, name in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": "tasks", "name": name}
        )
        for role in roles:
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0002_seed_task_priority"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
