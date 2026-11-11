"""Endpoints internos de enlaces del comprador (API §8).

- ``POST``/``GET /applications/{id}/buyer-access-links``
- ``DELETE /buyer-access-links/{link_id}``

El alcance es el de la solicitud: el asesor ve sus asignadas y el broker las de las
oportunidades que originó. Fuera del alcance se responde ``404``.
"""

from typing import Any, cast

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.models import CreditApplication
from apps.applications.services import applications_visible_to
from apps.identity import buyer_access
from apps.identity.buyer_access_serializers import (
    BuyerAccessLinkCreatedSerializer,
    BuyerAccessLinkCreateSerializer,
    BuyerAccessLinkSerializer,
)
from apps.identity.models import BuyerAccessLinkStatus, User, buyer_access_link_status_filter
from apps.identity.permissions import HasPermissionCode
from apps.identity.throttling import BuyerAccessIssueRateThrottle
from config.serializers import ErrorSerializer

BUYER_ACCESS_TAG = "Buyer access"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}


class _BuyerAccessView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(applications_visible_to(self.actor), pk=application_id)


class ApplicationBuyerAccessLinksView(_BuyerAccessView):
    required_permissions = {"GET": "buyer_access.read", "POST": "buyer_access.create"}
    throttle_classes = [BuyerAccessIssueRateThrottle]

    @extend_schema(
        tags=[BUYER_ACCESS_TAG],
        operation_id="buyer_access_links_list",
        summary="Historial de enlaces del comprador",
        description=(
            "Del más reciente al más antiguo, sin token ni URL. Un enlace `CONSUMED` "
            "trae la sesión que abrió."
        ),
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=BuyerAccessLinkStatus.values),
        ],
        responses={200: BuyerAccessLinkSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        queryset = buyer_access.links_queryset().filter(application=application)
        link_status = request.query_params.get("status")
        if link_status:
            if link_status not in BuyerAccessLinkStatus.values:
                raise ValidationError(
                    {
                        "status": [
                            "Valor no permitido. Opciones: "
                            f"{', '.join(BuyerAccessLinkStatus.values)}."
                        ]
                    }
                )
            queryset = queryset.filter(buyer_access_link_status_filter(link_status))
        page = self.paginate_queryset(queryset.order_by("-created_at"))
        return self.get_paginated_response(BuyerAccessLinkSerializer(page, many=True).data)

    @extend_schema(
        tags=[BUYER_ACCESS_TAG],
        operation_id="buyer_access_links_create",
        summary="Generar un enlace de acceso para el titular",
        description=(
            "El enlace es para el titular (`PRIMARY`) y sirve una sola vez. Revoca los "
            "enlaces pendientes anteriores de la solicitud; las sesiones abiertas siguen "
            "vivas. `url` lleva el token y solo aparece en esta respuesta. Con "
            "`EMAIL`, además se envía al correo del titular. Límite: 3 por hora por "
            "emisor y solicitud."
        ),
        request=BuyerAccessLinkCreateSerializer,
        responses={
            201: BuyerAccessLinkCreatedSerializer,
            400: _error("VALIDATION_ERROR (también: canal EMAIL sin correo del titular)"),
            409: _error("APPLICATION_CLOSED"),
            429: _error("RATE_LIMITED"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = BuyerAccessLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        issued = buyer_access.issue_access_link(
            self.actor,
            application,
            channel=data.get("delivery_channel") or buyer_access.default_channel(),
            expires_in_hours=data.get("expires_in_hours", settings.BUYER_ACCESS_LINK_DEFAULT_HOURS),
        )
        link = buyer_access.links_queryset().get(pk=issued.link.pk)
        body = BuyerAccessLinkCreatedSerializer(link, context={"url": issued.url}).data
        return Response(body, status=status.HTTP_201_CREATED)


class BuyerAccessLinkDetailView(_BuyerAccessView):
    required_permissions = {"DELETE": "buyer_access.revoke"}

    @extend_schema(
        tags=[BUYER_ACCESS_TAG],
        operation_id="buyer_access_links_destroy",
        summary="Revocar un enlace y cortar el acceso que dio",
        description=(
            "Pendiente: se revoca. Consumido: se revoca la sesión que abrió. Revocado o "
            "vencido: no cambia nada. Siempre responde `204`. El broker solo revoca los "
            "enlaces que generó."
        ),
        responses={204: None, **NOT_FOUND, **COMMON_ERRORS},
    )
    def delete(self, request: Request, link_id: Any) -> Response:
        link = get_object_or_404(buyer_access.links_visible_to(self.actor), pk=link_id)
        buyer_access.revoke_access_link(self.actor, link)
        return Response(status=status.HTTP_204_NO_CONTENT)
