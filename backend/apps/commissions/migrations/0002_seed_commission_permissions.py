"""Permisos de comisiones (``specs/TAREA-comisiones.md``, "Permisos y visibilidad").

Los planes y las liquidaciones son del administrador. ``commissions.read_own`` es del
asesor y del broker: cada uno ve solo su parte (``/me/commissions``).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISSIONS = [
    ("commission_plans.read", "Consultar planes de comisión", ["ADMIN"]),
    ("commission_plans.manage", "Administrar planes de comisión", ["ADMIN"]),
    ("commissions.read", "Consultar liquidaciones de comisión", ["ADMIN"]),
    ("commissions.manage", "Liquidar, anular y pagar comisiones", ["ADMIN"]),
    ("commissions.read_own", "Consultar mis comisiones", ["ADVISOR", "INDEPENDENT_BROKER"]),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    for code, name, roles in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": code.split(".")[0], "name": name}
        )
        for role in Role.objects.filter(code__in=roles):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Permission.objects.filter(code__in=[code for code, _, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("commissions", "0001_initial"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
