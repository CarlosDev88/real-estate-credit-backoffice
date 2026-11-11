from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

# Copia fija: una migración no debe depender del código vivo del modelo.
INTERNAL_ROLES = [
    (
        "ADMIN",
        "Administrador",
        "Acceso completo; administra usuarios, partners, proyectos, bancos, productos y "
        "requisitos documentales.",
    ),
    (
        "ADVISOR",
        "Asesor",
        "Gestiona clientes y solicitudes asignadas, tareas, documentos y radicaciones.",
    ),
    (
        "INDEPENDENT_BROKER",
        "Broker independiente",
        "Capta clientes, crea oportunidades, envía la invitación de autogestión y consulta "
        "el resumen de sus expedientes.",
    ),
    (
        "CONSTRUCTION_PARTNER",
        "Usuario de constructora",
        "Crea y edita los proyectos de su constructora.",
    ),
]


def create_roles(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Role = apps.get_model("identity", "Role")
    for code, name, description in INTERNAL_ROLES:
        Role.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description, "is_active": True},
        )


def delete_roles(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Role = apps.get_model("identity", "Role")
    Role.objects.filter(
        code__in=[code for code, _, _ in INTERNAL_ROLES],
        user_assignments__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0004_auth_sessions_password_reset_tokens"),
    ]

    operations = [
        migrations.RunPython(create_roles, delete_roles),
    ]
