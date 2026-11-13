from collections.abc import Mapping
from typing import Any

from django.db import models
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail


@extend_schema_field(OpenApiTypes.STR)
class ChoiceLabelField(serializers.Field):
    """Etiqueta visible de un código (``*_label``), de solo lectura.

    ``labels`` es la ``TextChoices`` del código o un mapa único código → texto: la
    etiqueta vive en un solo lugar del backend (REQ §8.5). ``source`` apunta al código;
    un código nulo da ``null`` (con ``allow_null=True``).
    """

    def __init__(self, labels: type[models.TextChoices] | Mapping[str, str], **kwargs: Any) -> None:
        kwargs["read_only"] = True
        super().__init__(**kwargs)
        self.labels: dict[str, str] = (
            {str(value): str(label) for value, label in labels.choices}
            if isinstance(labels, type)
            else dict(labels)
        )

    def to_representation(self, value: Any) -> str:
        return self.labels[str(value)]


class StrictSerializer(serializers.Serializer):
    """Serializer que rechaza campos no declarados (``additionalProperties: false``).

    Evita la asignación masiva: el cliente solo puede enviar los campos permitidos.
    """

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {
                        field: [ErrorDetail("Campo no permitido.", code="unknown_field")]
                        for field in unknown
                    }
                )
        return super().to_internal_value(data)


class ErrorDetailSerializer(serializers.Serializer):
    field = serializers.CharField(allow_null=True)
    code = serializers.CharField()
    message = serializers.CharField()
    # Opcional: recurso relacionado, por ejemplo el cliente que ya usa ese documento.
    resource_id = serializers.UUIDField(required=False)
    # Opcional: versión actual del recurso en un `409 STALE_VERSION` (API §6).
    current_version = serializers.IntegerField(required=False)


class ErrorSerializer(serializers.Serializer):
    """Esquema OpenAPI del cuerpo de error común."""

    code = serializers.CharField()
    message = serializers.CharField()
    details = ErrorDetailSerializer(many=True)
    request_id = serializers.CharField(allow_null=True)
