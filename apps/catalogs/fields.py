"""Campo de serializer para referenciar un valor de catálogo por su código.

Lo usan los demás módulos para cumplir la regla 6 del esquema: "los catalog_items
usados por cada FK deben pertenecer al catálogo esperado". Ejemplo::

    class ApplicationCreateSerializer(StrictSerializer):
        purpose = CatalogItemCodeField(catalog_code="loan_purpose")

El cliente envía ``"purpose": "PURCHASE_NEW"`` y ``validated_data["purpose"]`` es
la instancia de ``CatalogItem``. Solo acepta ítems activos y vigentes hoy.
"""

from typing import Any

from rest_framework import serializers

from apps.catalogs.models import CatalogItem
from apps.catalogs.services import today


class CatalogItemCodeField(serializers.Field):
    default_error_messages = {
        "invalid": "Debe ser un código de texto.",
        "not_found": "El código «{code}» no existe en el catálogo {catalog}.",
        "unavailable": "El valor «{code}» no está activo o vigente.",
    }

    def __init__(self, *, catalog_code: str, allow_unavailable: bool = False, **kwargs: Any):
        self.catalog_code = catalog_code
        # True solo para lecturas o datos históricos: acepta ítems inactivos o vencidos.
        self.allow_unavailable = allow_unavailable
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> CatalogItem:
        if not isinstance(data, str) or not data:
            self.fail("invalid")
        item = (
            CatalogItem.objects.select_related("catalog")
            .filter(catalog__code=self.catalog_code, code=data)
            .first()
        )
        if item is None:
            self.fail("not_found", code=data, catalog=self.catalog_code)
        assert item is not None
        if not self.allow_unavailable and not item.is_available_on(today()):
            self.fail("unavailable", code=data)
        return item

    def to_representation(self, value: CatalogItem) -> str:
        return value.code
