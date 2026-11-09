"""Serializers de los enlaces de acceso del comprador (API §8), vista interna."""

from typing import Any

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.serializers import UserRefSerializer
from apps.identity.buyer_access import CHANNEL_CATALOG
from apps.identity.models import BuyerAccessLinkStatus, BuyerSession
from config.serializers import StrictSerializer


class BuyerAccessLinkCreateSerializer(StrictSerializer):
    delivery_channel = CatalogItemCodeField(
        catalog_code=CHANNEL_CATALOG,
        required=False,
        help_text="Código del catálogo `buyer_access_channel`. Por omisión, `COPY_LINK`.",
    )
    expires_in_hours = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Vigencia del enlace en horas. Por omisión, 72; como máximo, 168.",
    )

    def validate_expires_in_hours(self, value: int) -> int:
        maximum = settings.BUYER_ACCESS_LINK_MAX_HOURS
        if value > maximum:
            raise serializers.ValidationError(f"Debe ser como máximo {maximum}.")
        return value


class BuyerSessionSummarySerializer(serializers.Serializer):
    """Sesión que abrió un enlace consumido. Nunca expone su hash."""

    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    last_seen_at = serializers.DateTimeField(allow_null=True)
    is_active = serializers.SerializerMethodField()

    def get_is_active(self, session: BuyerSession) -> bool:
        return session.is_active_at()


class BuyerAccessLinkSerializer(serializers.Serializer):
    """Enlace sin token: es la forma del listado (API §8, "historial sin token")."""

    id = serializers.UUIDField()
    application_id = serializers.UUIDField()
    client_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=BuyerAccessLinkStatus.choices)
    delivery_channel = CatalogItemRefSerializer(source="delivery_channel_item", allow_null=True)
    created_by = UserRefSerializer(allow_null=True)
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    consumed_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    session = BuyerSessionSummarySerializer(allow_null=True)


class BuyerAccessLinkCreatedSerializer(BuyerAccessLinkSerializer):
    """Respuesta de la emisión: la única que lleva ``url`` con el token."""

    url = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, link: Any) -> str:
        return str(self.context["url"])
