"""Catálogo `participant_role` (TAREA-brechas-3-demo, parte 1).

Etiquetas del papel de cada participante de la solicitud (titular, co-solicitante y
deudor solidario), para que el front no escriba esos textos al agregar un participante.
Lo administra el backend (``is_manageable=False``): los códigos son los de
``ParticipantRole`` y sus etiquetas también (una prueba exige que coincidan).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CATALOGS = [
    (
        "participant_role",
        "Papel del participante",
        "Papel de cada participante en la solicitud de crédito.",
        [
            ("PRIMARY", "Titular"),
            ("CO_APPLICANT", "Co-solicitante"),
            ("SOLIDARY_DEBTOR", "Deudor solidario"),
        ],
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
        ("applications", "0005_application_completeness_snapshot"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
