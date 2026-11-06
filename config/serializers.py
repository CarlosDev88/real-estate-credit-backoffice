from collections.abc import Mapping
from typing import Any

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail


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
