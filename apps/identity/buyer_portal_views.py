"""Endpoints del comprador (API §8).

- ``POST /buyer-access/consume`` (público)
- ``GET /buyer/session`` y ``POST /buyer/session/logout``
- ``GET /buyer/processes`` y ``GET /buyer/applications/{id}``

Las vistas ``/buyer/*`` solo aceptan la cookie del comprador. El ``application_id`` de
la ruta debe ser el de la sesión; cualquier otro responde ``404``.
"""

from typing import Any, cast

from django.middleware.csrf import rotate_token
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.concurrency import with_etag
from apps.applications.models import CreditApplication
from apps.identity import buyer_portal, buyer_sessions
from apps.identity.authentication import enforce_csrf
from apps.identity.buyer_authentication import BuyerSessionAuthentication, IsBuyerSession
from apps.identity.buyer_portal_serializers import (
    BuyerAccessConsumeResponseSerializer,
    BuyerAccessConsumeSerializer,
    BuyerApplicationDetailSerializer,
    BuyerProcessSerializer,
    BuyerSessionResponseSerializer,
)
from apps.identity.cookies import (
    buyer_session_cookie_name,
    clear_buyer_session_cookie,
    set_buyer_session_cookie,
)
from apps.identity.exceptions import BuyerSessionExpired
from apps.identity.models import BuyerSession
from apps.identity.throttling import BuyerAccessConsumeRateThrottle
from config.serializers import ErrorSerializer

BUYER_PORTAL_TAG = "Buyer portal"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


SESSION_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (no es la solicitud de la sesión)")}


def _no_store(response: Response) -> Response:
    # Respuestas con datos personales o que abren una sesión: sin caché intermedia.
    response["Cache-Control"] = "no-store"
    return response


class BuyerPortalView(GenericAPIView):
    """Base de las vistas ``/buyer/*``: solo la sesión del comprador autentica."""

    authentication_classes = [BuyerSessionAuthentication]
    permission_classes = [IsBuyerSession]

    @property
    def buyer_session(self) -> BuyerSession:
        return cast(BuyerSession, self.request.auth)

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(
            buyer_portal.buyer_application_detail(self.buyer_session), pk=application_id
        )

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        return _no_store(super().finalize_response(request, response, *args, **kwargs))

    def handle_exception(self, exc: Exception) -> Response:
        response = super().handle_exception(exc)
        if isinstance(exc, BuyerSessionExpired):
            # Evita que el navegador siga enviando una cookie que ya no sirve.
            clear_buyer_session_cookie(response)
        return response


class BuyerAccessConsumeView(APIView):
    """Público: una cookie del comprador vencida no debe impedir consumir otro enlace."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes = [BuyerAccessConsumeRateThrottle]

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_access_consume",
        summary="Consumir el enlace mágico y abrir la sesión del comprador",
        description=(
            "El enlace sirve una sola vez. Fija la cookie de la sesión y rota el token "
            "CSRF (`app_csrf`). Cierra las otras sesiones del comprador en la misma "
            "solicitud. El frontend debe quitar el token de la URL apenas lo consuma. "
            "Límite: 5 intentos por hora por IP."
        ),
        request=BuyerAccessConsumeSerializer,
        responses={
            200: BuyerAccessConsumeResponseSerializer,
            400: _error("VALIDATION_ERROR"),
            401: _error(
                "MAGIC_LINK_INVALID, MAGIC_LINK_EXPIRED, MAGIC_LINK_CONSUMED o MAGIC_LINK_REVOKED"
            ),
            429: _error("RATE_LIMITED"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = BuyerAccessConsumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued = buyer_sessions.consume_access_link(
            request=request, raw_token=serializer.validated_data["token"]
        )
        response = Response(BuyerAccessConsumeResponseSerializer(issued).data)
        set_buyer_session_cookie(response, token=issued.token, expires_at=issued.expires_at)
        # Token CSRF nuevo por sesión, contra la fijación de sesión.
        rotate_token(request)
        return _no_store(response)


class BuyerSessionView(BuyerPortalView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_session_retrieve",
        summary="Sesión del comprador, su nombre y la solicitud a la que da acceso",
        responses={200: BuyerSessionResponseSerializer, **SESSION_ERRORS},
    )
    def get(self, request: Request) -> Response:
        return Response(BuyerSessionResponseSerializer(self.buyer_session).data)


class BuyerLogoutView(APIView):
    """Pública con CSRF, como el logout interno: una sesión vencida igual borra la cookie."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_session_logout",
        summary="Cerrar la sesión del comprador",
        description="Revoca la sesión de la cookie y la borra. Siempre responde `204`.",
        request=None,
        responses={204: None, 403: _error("CSRF_FAILED")},
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        buyer_sessions.logout_buyer_session(request.COOKIES.get(buyer_session_cookie_name()))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_buyer_session_cookie(response)
        return response


class BuyerProcessesView(BuyerPortalView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_processes_list",
        summary="Procesos del comprador",
        description="Solo el proceso de la solicitud de la sesión vigente.",
        responses={200: BuyerProcessSerializer(many=True), **SESSION_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(buyer_portal.session_applications(self.buyer_session))
        return self.get_paginated_response(BuyerProcessSerializer(page, many=True).data)


class BuyerApplicationDetailView(BuyerPortalView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_applications_retrieve",
        summary="Solicitud del comprador",
        description=(
            "Estado público, siguiente acción, progreso, participantes, inmueble y "
            "financiación. No incluye notas, asesor ni evaluaciones bancarias. La "
            "versión viaja también en `ETag`."
        ),
        responses={200: BuyerApplicationDetailSerializer, **NOT_FOUND, **SESSION_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        response = Response(BuyerApplicationDetailSerializer(application).data)
        return with_etag(response, application.version)
