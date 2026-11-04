"""Documenta en OpenAPI los campos propios del módulo catalogs."""

from typing import Any

from drf_spectacular.extensions import OpenApiSerializerFieldExtension


class CatalogItemCodeFieldExtension(OpenApiSerializerFieldExtension):
    target_class = "apps.catalogs.fields.CatalogItemCodeField"

    def map_serializer_field(self, auto_schema: Any, direction: Any) -> dict[str, Any]:
        catalog_code = self.target.catalog_code
        return {
            "type": "string",
            "description": (
                f"Código de un valor activo del catálogo `{catalog_code}`. Consulta los "
                f"valores en `/api/v1/metadata/catalogs/{catalog_code}`."
            ),
        }
