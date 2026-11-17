"""Notificaciones del comprador (API §21.2) y su seguimiento en el backoffice.

- ``GET /buyer/notifications``, ``GET /buyer/notifications/unread-count``,
  ``PATCH /buyer/notifications/{id}/read`` y ``POST /buyer/notifications/read-all``:
  solo la sesión del comprador, sobre las notificaciones de su cliente en la solicitud
  de la sesión. Un consentimiento pendiente (``CONSENT_REQUIRED``) o una solicitud
  terminada no impiden leerlas ni marcarlas.
- ``GET /applications/{id}/notifications``: el administrador y el asesor asignado, con
  las entregas de cada una.
"""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.services import applications_visible_to
from apps.identity.buyer_authentication import BuyerSessionAuthentication, IsBuyerSession
from apps.identity.buyer_portal_views import BUYER_PORTAL_TAG, SESSION_ERRORS
from apps.identity.models import BuyerSession, User
from apps.identity.permissions import HasPermissionCode
from apps.notifications import services
from apps.notifications.serializers import (
    ApplicationNotificationSerializer,
    BuyerNotificationFilterSerializer,
    BuyerNotificationSerializer,
    NotificationCountSerializer,
)
from config.serializers import ErrorSerializer

NOTIFICATIONS_TAG = "Notifications"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (no es una notificación de la sesión)")}


class BuyerNotificationView(GenericAPIView):
    """Solo la cookie del comprador. Sin ``ConsentsAccepted`` ni ``ApplicationNotClosed``:
    marcar como leída no cambia el expediente."""

    authentication_classes = [BuyerSessionAuthentication]
    permission_classes = [IsBuyerSession]

    @property
    def buyer_session(self) -> BuyerSession:
        return cast(BuyerSession, self.request.auth)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class BuyerNotificationListView(BuyerNotificationView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_notifications_list",
        summary="Notificaciones del comprador",
        description=(
            "Las de la solicitud de la sesión, de la más nueva a la más vieja. Con "
            "`unread=true`, solo las no leídas."
        ),
        parameters=[
            OpenApiParameter("unread", bool, description="Solo las no leídas.", required=False)
        ],
        responses={
            200: BuyerNotificationSerializer(many=True),
            400: _error("VALIDATION_ERROR"),
            **SESSION_ERRORS,
        },
    )
    def get(self, request: Request) -> Response:
        filters = BuyerNotificationFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        notifications = services.buyer_notifications(self.buyer_session)
        if filters.validated_data["unread"]:
            notifications = notifications.filter(read_at__isnull=True)
        page = self.paginate_queryset(notifications)
        return self.get_paginated_response(BuyerNotificationSerializer(page, many=True).data)


class BuyerNotificationUnreadCountView(BuyerNotificationView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_notifications_unread_count",
        summary="Cantidad de notificaciones sin leer",
        description="Para el número de la navegación del portal.",
        responses={200: NotificationCountSerializer, **SESSION_ERRORS},
    )
    def get(self, request: Request) -> Response:
        count = services.unread_count(self.buyer_session)
        return Response(NotificationCountSerializer({"count": count}).data)


class BuyerNotificationReadView(BuyerNotificationView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_notifications_read",
        summary="Marcar una notificación como leída",
        description=(
            "Sin cuerpo. Es idempotente: una notificación ya leída conserva su `read_at`. "
            "La de otro comprador o de otra solicitud responde `404`."
        ),
        request=None,
        responses={200: BuyerNotificationSerializer, **NOT_FOUND, **SESSION_ERRORS},
    )
    def patch(self, request: Request, notification_id: Any) -> Response:
        notification = get_object_or_404(
            services.buyer_notifications(self.buyer_session), pk=notification_id
        )
        services.mark_read(notification)
        return Response(BuyerNotificationSerializer(notification).data)


class BuyerNotificationReadAllView(BuyerNotificationView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_notifications_read_all",
        summary="Marcar todas las notificaciones como leídas",
        description="Sin cuerpo. `count` es la cantidad que estaba sin leer y se marcó.",
        request=None,
        responses={200: NotificationCountSerializer, **SESSION_ERRORS},
    )
    def post(self, request: Request) -> Response:
        count = services.mark_all_read(self.buyer_session)
        return Response(NotificationCountSerializer({"count": count}).data)


class ApplicationNotificationListView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "notifications.read"}

    @extend_schema(
        tags=[NOTIFICATIONS_TAG],
        operation_id="applications_notifications_list",
        summary="Notificaciones de la solicitud y sus entregas",
        description=(
            "Lo que recibió el comprador, de la más nueva a la más vieja, con cada entrega "
            "(portal y correo): estado, intentos y último error, para saber si el correo "
            "salió. Para el administrador y el asesor asignado (`notifications.read`)."
        ),
        responses={
            200: ApplicationNotificationSerializer(many=True),
            401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
            403: _error("PERMISSION_DENIED"),
            404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)"),
        },
    )
    def get(self, request: Request, application_id: Any) -> Response:
        actor = cast(User, request.user)
        application = get_object_or_404(applications_visible_to(actor), pk=application_id)
        page = self.paginate_queryset(services.application_notifications(application))
        return self.get_paginated_response(ApplicationNotificationSerializer(page, many=True).data)
