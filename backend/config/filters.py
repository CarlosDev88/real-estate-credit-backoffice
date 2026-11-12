"""Filtros con lista permitida (sección 28.2): un parámetro desconocido es un error."""

import uuid
from typing import Any

from django.db.models import F, OrderBy, QuerySet
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request

_TRUE = {"true", "1"}
_FALSE = {"false", "0"}


class StrictOrderingFilter(OrderingFilter):
    """``?ordering=`` solo acepta los campos de ``ordering_fields`` de la vista.

    Con ``ordering_nulls_last = True`` en la vista, los nulos van al final en los dos
    sentidos (en PostgreSQL, por omisión, van al principio al ordenar descendente).
    """

    def filter_queryset(self, request: Request, queryset: QuerySet[Any], view: Any) -> Any:
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        if getattr(view, "ordering_nulls_last", False):
            return queryset.order_by(*(nulls_last(term) for term in ordering))
        return queryset.order_by(*ordering)

    def get_ordering(self, request: Request, queryset: QuerySet[Any], view: Any) -> Any:
        params = request.query_params.get(self.ordering_param)
        if params:
            requested = [param.strip() for param in params.split(",") if param.strip()]
            allowed = {
                field for field, _ in self.get_valid_fields(queryset, view, {"request": request})
            }
            invalid = [term for term in requested if term.lstrip("-") not in allowed]
            if invalid:
                raise ValidationError(
                    {self.ordering_param: [f"Campo de orden no permitido: {', '.join(invalid)}."]}
                )
        return super().get_ordering(request, queryset, view)


def nulls_last(term: str) -> OrderBy:
    """``"-campo"`` → ``F("campo").desc(nulls_last=True)``; ``"campo"`` → ascendente."""
    if term.startswith("-"):
        return F(term[1:]).desc(nulls_last=True)
    return F(term).asc(nulls_last=True)


def parse_uuid_param(request: Request, name: str) -> uuid.UUID | None:
    value = request.query_params.get(name)
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError({name: ["Debe ser un UUID válido."]}) from exc


def parse_bool_param(request: Request, name: str) -> bool | None:
    value = request.query_params.get(name)
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValidationError({name: ["Debe ser true o false."]})
