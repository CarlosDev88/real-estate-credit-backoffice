from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("users.read", "users", "Consultar usuarios internos"),
    ("users.create", "users", "Crear usuarios internos"),
    ("users.update", "users", "Editar usuarios internos"),
    ("users.manage_status", "users", "Activar y desactivar usuarios internos"),
    ("roles.read", "roles", "Consultar roles y permisos"),
    ("roles.assign", "roles", "Asignar roles a usuarios"),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    admin = Role.objects.filter(code="ADMIN").first()
    for code, module, name in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        if admin:
            RolePermission.objects.get_or_create(role=admin, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0007_seed_invitation_permissions"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
