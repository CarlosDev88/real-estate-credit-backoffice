from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("invitations.read", "Consultar invitaciones internas"),
    ("invitations.create", "Crear y reenviar invitaciones internas"),
    ("invitations.revoke", "Revocar invitaciones internas"),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    admin = Role.objects.filter(code="ADMIN").first()
    for code, name in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": "invitations", "name": name}
        )
        if admin:
            RolePermission.objects.get_or_create(role=admin, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0006_internal_invitations"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
