"""Motivos de cierre del catálogo `application_transition_reason`.

`CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` exigen motivo (Parte 6). Son una
propuesta inicial editable desde la administración de catálogos; `OTHER` ya existía.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CATALOG_CODE = "application_transition_reason"
# (código, etiqueta)
CLOSING_REASONS = [
    ("CLIENT_UNREACHABLE", "No fue posible contactar al cliente"),
    ("INSUFFICIENT_CAPACITY", "Capacidad de pago insuficiente"),
    ("CLIENT_DECLINED_PURCHASE", "El cliente desistió de la compra"),
    ("BETTER_RATE_ELSEWHERE", "Consiguió mejor tasa en otra entidad"),
    ("FASTER_ELSEWHERE", "Otra entidad le respondió más rápido"),
    ("EXISTING_BANK_RELATIONSHIP", "Prefirió el banco con el que ya tiene relación"),
    ("SOLD_OTHER_PROPERTY", "Vendió otro inmueble y compra con esos recursos"),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    catalog = Catalog.objects.get(code=CATALOG_CODE)
    last = (
        CatalogItem.objects.filter(catalog=catalog)
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    ) or 0
    # Antes de `OTHER`, que queda al final de la lista.
    other = CatalogItem.objects.filter(catalog=catalog, code="OTHER").first()
    for index, (code, label) in enumerate(CLOSING_REASONS, start=1):
        CatalogItem.objects.get_or_create(
            catalog=catalog,
            code=code,
            defaults={"label": label, "sort_order": last + index * 10},
        )
    if other is not None:
        other.sort_order = last + (len(CLOSING_REASONS) + 1) * 10
        other.save(update_fields=["sort_order"])


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    CatalogItem.objects.filter(
        catalog__code=CATALOG_CODE, code__in=[code for code, _ in CLOSING_REASONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0002_seed_permissions_catalogs_transitions"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
