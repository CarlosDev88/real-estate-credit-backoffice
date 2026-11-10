"""Permisos, canal de entrega y consentimientos del acceso del comprador (paso 9).

- `buyer_access.*`: emiten, listan y revocan enlaces el administrador, el asesor (en sus
  solicitudes asignadas) y el broker (en las de sus oportunidades). El partner no.
- `consents.read`: evidencias de consentimiento de una solicitud; el broker no las ve.
- `buyer_access_channel`: lo administra el backend (`is_manageable = false`), porque el
  servicio de emisión decide según el código (`EMAIL` envía el correo).
- Consentimientos v1 con texto **provisional**: el texto legal está pendiente de
  validación (REQUERIMIENTOS §12). Las versiones nuevas se publican con otra migración.
"""

import hashlib
from datetime import UTC, datetime

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

ADMIN = "ADMIN"
ADVISOR = "ADVISOR"
BROKER = "INDEPENDENT_BROKER"

# (código, módulo, nombre, roles)
PERMISSIONS = [
    (
        "buyer_access.create",
        "buyer_access",
        "Generar enlaces de acceso del comprador",
        [ADMIN, ADVISOR, BROKER],
    ),
    (
        "buyer_access.read",
        "buyer_access",
        "Consultar los enlaces de acceso del comprador",
        [ADMIN, ADVISOR, BROKER],
    ),
    (
        "buyer_access.revoke",
        "buyer_access",
        "Revocar enlaces y sesiones del comprador",
        [ADMIN, ADVISOR, BROKER],
    ),
    ("consents.read", "consents", "Consultar consentimientos de solicitudes", [ADMIN, ADVISOR]),
]

CHANNEL_CATALOG = "buyer_access_channel"
CHANNELS = [
    ("COPY_LINK", "Copiar enlace"),
    ("EMAIL", "Correo electrónico"),
]

# 2026-01-01 00:00 en Bogotá (UTC-5).
EFFECTIVE_FROM = datetime(2026, 1, 1, 5, 0, tzinfo=UTC)

# (código, título, texto)
CONSENTS = [
    (
        "DATA_PROCESSING",
        "Autorización de tratamiento de datos personales",
        "TEXTO PROVISIONAL, PENDIENTE DE VALIDACIÓN LEGAL.\n\n"
        "Autorizo de manera previa, expresa e informada el tratamiento de mis datos "
        "personales, incluidos los financieros, para gestionar mi solicitud de crédito de "
        "vivienda: verificar mi identidad, evaluar las condiciones de los productos "
        "bancarios, preparar mi expediente y presentarlo a la entidad financiera que "
        "elija, conforme a la Ley 1581 de 2012 y sus decretos reglamentarios. Puedo "
        "conocer, actualizar, rectificar y suprimir mis datos, y revocar esta "
        "autorización, por los canales de atención dispuestos para ello.",
    ),
    (
        "CO_APPLICANT_AUTHORIZATION",
        "Declaración de autorización de los co-solicitantes",
        "TEXTO PROVISIONAL, PENDIENTE DE VALIDACIÓN LEGAL.\n\n"
        "Declaro que cuento con la autorización previa, expresa e informada de las "
        "personas que participan conmigo en esta solicitud de crédito para registrar y "
        "compartir sus datos personales y financieros con el fin de gestionar la "
        "solicitud, y que les informé la finalidad del tratamiento y sus derechos "
        "conforme a la Ley 1581 de 2012.",
    ),
]


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    Catalog = apps.get_model("catalogs", "Catalog")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    ConsentDefinition = apps.get_model("identity", "ConsentDefinition")

    roles = {role.code: role for role in Role.objects.all()}
    for code, module, name, role_codes in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"module": module, "name": name}
        )
        for role_code in role_codes:
            if role_code in roles:
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    catalog, _ = Catalog.objects.get_or_create(
        code=CHANNEL_CATALOG,
        defaults={
            "name": "Canal de entrega del enlace del comprador",
            "description": "Cómo llega al comprador su enlace de acceso.",
            "is_public": False,
            "is_manageable": False,
        },
    )
    for index, (item_code, label) in enumerate(CHANNELS):
        CatalogItem.objects.get_or_create(
            catalog=catalog,
            code=item_code,
            defaults={"label": label, "sort_order": (index + 1) * 10},
        )

    # El modelo histórico no tiene el `save()` que calcula la huella.
    for code, title, body in CONSENTS:
        ConsentDefinition.objects.get_or_create(
            code=code,
            version=1,
            defaults={
                "title": title,
                "body": body,
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "effective_from": EFFECTIVE_FROM,
            },
        )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Permission = apps.get_model("identity", "Permission")
    CatalogItem = apps.get_model("catalogs", "CatalogItem")
    Catalog = apps.get_model("catalogs", "Catalog")
    ConsentDefinition = apps.get_model("identity", "ConsentDefinition")

    ConsentDefinition.objects.filter(
        code__in=[code for code, _, _ in CONSENTS], version=1
    ).delete()
    CatalogItem.objects.filter(catalog__code=CHANNEL_CATALOG).delete()
    Catalog.objects.filter(code=CHANNEL_CATALOG).delete()
    Permission.objects.filter(code__in=[code for code, *_ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0009_buyer_access_and_consents"),
        ("catalogs", "0002_seed_permissions_and_catalogs"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
