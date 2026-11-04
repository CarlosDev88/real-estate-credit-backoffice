from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param


class StandardResultsSetPagination(PageNumberPagination):
    """Lista paginada de la sección 5.2: ``items``, ``page``, ``page_size``, ``total``.

    ``next`` y ``previous`` son rutas relativas (``/api/v1/...?page=2``), no URLs
    absolutas, para no depender del host con el que llegó la petición.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def _relative_link(self, page_number: int | None) -> str | None:
        if page_number is None:
            return None
        assert self.request is not None
        url = self.request.get_full_path()
        if page_number == 1:
            return remove_query_param(url, self.page_query_param)
        return replace_query_param(url, self.page_query_param, page_number)

    def get_paginated_response(self, data: Any) -> Response:
        assert self.page is not None
        page = self.page
        return Response(
            OrderedDict(
                [
                    ("items", data),
                    ("page", page.number),
                    ("page_size", page.paginator.per_page),
                    ("total", page.paginator.count),
                    (
                        "next",
                        self._relative_link(page.next_page_number() if page.has_next() else None),
                    ),
                    (
                        "previous",
                        self._relative_link(
                            page.previous_page_number() if page.has_previous() else None
                        ),
                    ),
                ]
            )
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["items", "page", "page_size", "total", "next", "previous"],
            "properties": {
                "items": schema,
                "page": {"type": "integer", "example": 1},
                "page_size": {"type": "integer", "example": 25},
                "total": {"type": "integer", "example": 128},
                "next": {"type": "string", "nullable": True, "example": "/api/v1/x?page=2"},
                "previous": {"type": "string", "nullable": True, "example": None},
            },
        }
