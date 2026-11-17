"""Catálogo `task_priority` de las tareas (API §15.2).

Es una propuesta inicial editable desde la administración de catálogos. Una tarea nueva
sin prioridad usa `MEDIUM`.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CATALOG_CODE = "task_priority"
ITEMS = [("LOW", "Baja"), ("MEDIUM", "Media"), ("HIGH", "Alta")]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    catalog, _ = Catalog.objects.get_or_create(
        code=CATALOG_CODE,
        defaults={
            "name": "Prioridad de tareas",
            "description": "Prioridad de una tarea de seguimiento.",
            "is_public": False,
        },
    )
    for index, (code, label) in enumerate(ITEMS, start=1):
        CatalogItem.objects.get_or_create(
            catalog=catalog, code=code, defaults={"label": label, "sort_order": index * 10}
        )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    CatalogItem.objects.filter(catalog__code=CATALOG_CODE).delete()
    Catalog.objects.filter(code=CATALOG_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0001_initial"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
