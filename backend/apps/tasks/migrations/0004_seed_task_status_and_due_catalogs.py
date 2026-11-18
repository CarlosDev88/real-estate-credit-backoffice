"""Catálogos `task_status` y `task_due` (TAREA-brechas-2, parte 3).

Etiquetas del estado de una tarea y de las opciones del filtro `due` de `GET /tasks`,
para que el front no escriba esos textos. Los administra el backend
(``is_manageable=False``) y sus códigos son los mismos valores del contrato: los de
`task_due` van en minúsculas, como el filtro. Las etiquetas son las de ``TaskStatus`` y
``DueWindow`` (una prueba exige que coincidan).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CATALOGS = [
    (
        "task_status",
        "Estado de tarea",
        "Etiquetas de los estados de una tarea de seguimiento.",
        [("PENDING", "Pendiente"), ("COMPLETED", "Completada"), ("CANCELLED", "Cancelada")],
    ),
    (
        "task_due",
        "Vencimiento de tareas",
        "Opciones del filtro `due` de las tareas (fecha de Bogotá).",
        [("overdue", "Vencidas"), ("today", "Hoy"), ("upcoming", "Próximas")],
    ),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    for code, name, description, items in CATALOGS:
        catalog, _ = Catalog.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_public": False,
                "is_manageable": False,
            },
        )
        for index, (item_code, label) in enumerate(items, start=1):
            CatalogItem.objects.get_or_create(
                catalog=catalog, code=item_code, defaults={"label": label, "sort_order": index * 10}
            )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    codes = [code for code, *_ in CATALOGS]
    CatalogItem.objects.filter(catalog__code__in=codes).delete()
    Catalog.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0003_seed_task_permissions"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
