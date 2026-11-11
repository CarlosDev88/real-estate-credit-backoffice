"""Permisos del módulo banking y bancos de prueba del MVP.

Permisos según la matriz de acceso (sección 8.6 de los requerimientos): el
administrador administra bancos, productos y reglas; el asesor solo consulta. Broker
y partner no consultan esta configuración: elegir banco dentro de una solicitud se
resolverá en el paso 8 (``/applications/{id}/eligible-bank-products``).

Bancos de prueba (sección 2 de los requerimientos y 23.2 de la API): Bancolombia,
Fondo Nacional del Ahorro y Banco de Bogotá, cada uno con un producto hipotecario
activo que admite las tres finalidades del MVP. Los documentos no dan montos ni
plazos, así que los rangos quedan vacíos, y no se siembra ninguna regla: el ejemplo
`MAX_LTV_NEW_HOME` de la sección 23.3 es conceptual. Todo se edita después por API.
"""

from datetime import date

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"

# (código, módulo, nombre, roles)
PERMISSIONS = [
    ("banks.read", "banks", "Consultar bancos y productos", [ADMIN, ADVISOR]),
    ("banks.create", "banks", "Crear bancos y productos", [ADMIN]),
    ("banks.update", "banks", "Editar, activar y desactivar bancos y productos", [ADMIN]),
    ("bank_rules.read", "bank_rules", "Consultar reglas bancarias", [ADMIN, ADVISOR]),
    ("bank_rules.create", "bank_rules", "Crear reglas bancarias", [ADMIN]),
    ("bank_rules.update", "bank_rules", "Editar y probar reglas bancarias", [ADMIN]),
    ("bank_rules.publish", "bank_rules", "Publicar y desactivar reglas bancarias", [ADMIN]),
]

# (código del banco, nombre, nombre del producto)
BANKS = [
    ("BANCOLOMBIA", "Bancolombia", "Crédito hipotecario"),
    ("FNA", "Fondo Nacional del Ahorro", "Crédito hipotecario"),
    ("BANCO_BOGOTA", "Banco de Bogotá", "Crédito de vivienda"),
]
PRODUCT_CODE = "MORTGAGE"
PRODUCT_TYPE = "MORTGAGE"
PURPOSES = ["PURCHASE_NEW", "PURCHASE_USED", "HOME_IMPROVEMENT"]
VALID_FROM = date(2026, 1, 1)


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    Bank = apps.get_model("banking", "Bank")
    BankProduct = apps.get_model("banking", "BankProduct")
    BankProductPurpose = apps.get_model("banking", "BankProductPurpose")

    roles = {role.code: role for role in Role.objects.all()}
    for code, module, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    product_type = CatalogItem.objects.get(catalog__code="bank_product_type", code=PRODUCT_TYPE)
    purposes = list(CatalogItem.objects.filter(catalog__code="loan_purpose", code__in=PURPOSES))
    for bank_code, bank_name, product_name in BANKS:
        bank, _ = Bank.objects.get_or_create(code=bank_code, defaults={"name": bank_name})
        product, created = BankProduct.objects.get_or_create(
            bank=bank,
            code=PRODUCT_CODE,
            defaults={
                "name": product_name,
                "product_type_item": product_type,
                "valid_from": VALID_FROM,
            },
        )
        if created:
            BankProductPurpose.objects.bulk_create(
                BankProductPurpose(bank_product=product, purpose_item=purpose)
                for purpose in purposes
            )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Bank = apps.get_model("banking", "Bank")
    BankProduct = apps.get_model("banking", "BankProduct")

    bank_codes = [code for code, *_ in BANKS]
    BankProduct.objects.filter(bank__code__in=bank_codes, code=PRODUCT_CODE).delete()
    Bank.objects.filter(code__in=bank_codes).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("banking", "0001_initial"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
        ("identity", "0005_seed_internal_roles"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
