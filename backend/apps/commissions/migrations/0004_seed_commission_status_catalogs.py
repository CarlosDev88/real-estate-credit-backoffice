"""Catálogos `commission_settlement_status` y `commission_share_status`
(TAREA-brechas-3-demo, parte 1).

Etiquetas del estado de una liquidación y de cada parte, para que los filtros de
comisiones no escriban esos textos. Los administra el backend (``is_manageable=False``):
los códigos son los de ``SettlementStatus`` y ``ShareStatus`` y sus etiquetas también
(una prueba exige que coincidan).
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CATALOGS = [
    (
        "commission_settlement_status",
        "Estado de liquidación de comisión",
        "Estados de una liquidación de comisión.",
        [("ACTIVE", "Vigente"), ("VOIDED", "Anulada")],
    ),
    (
        "commission_share_status",
        "Estado de parte de comisión",
        "Estados de cada parte (beneficiario) de una liquidación de comisión.",
        [("PENDING", "Pendiente de pago"), ("PAID", "Pagada"), ("VOIDED", "Anulada")],
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
        ("commissions", "0003_settlement_response_active"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
