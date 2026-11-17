"""Endpoints del comprador (API §8).

- ``POST /buyer-access/consume`` (público)
- ``GET /buyer/session`` y ``POST /buyer/session/logout``
- ``GET /buyer/processes`` y ``GET /buyer/applications/{id}``
- ``GET``/``POST /buyer/applications/{id}/consents``

Las vistas ``/buyer/*`` solo aceptan la cookie del comprador. El ``application_id`` de
la ruta debe ser el de la sesión; cualquier otro responde ``404``. Las escrituras
responden ``403 CONSENT_REQUIRED`` mientras falte un consentimiento obligatorio, salvo
la aceptación de consentimientos y el logout.
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
from apps.catalogs.views import (
    METADATA_CATALOG_DESCRIPTION,
    METADATA_CATALOG_PARAMETERS,
    METADATA_CATALOG_RESPONSES,
    metadata_catalog_response,
)
from apps.identity import buyer_portal, buyer_sessions, consents
from apps.identity.authentication import enforce_csrf
from apps.identity.buyer_authentication import (
    ApplicationNotClosed,
    BuyerSessionAuthentication,
    ConsentsAccepted,
    IsBuyerSession,
)
from apps.identity.buyer_portal_serializers import (
    BuyerAccessConsumeResponseSerializer,
    BuyerAccessConsumeSerializer,
    BuyerApplicationDetailSerializer,
    BuyerConsentActionSerializer,
    BuyerConsentListSerializer,
    BuyerConsentRecordSerializer,
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
from config.openapi import etag_response_headers
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
    permission_classes = [IsBuyerSession, ApplicationNotClosed, ConsentsAccepted]

    @property
    def buyer_session(self) -> BuyerSession:
        return cast(BuyerSession, self.request.auth)

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(
            buyer_portal.buyer_application_detail(self.buyer_session), pk=application_id
        )

    def ensure_session_application(self, application_id: Any) -> CreditApplication:
        """``404`` si la ruta no es la solicitud de la sesión."""
        return get_object_or_404(
            buyer_portal.session_applications(self.buyer_session), pk=application_id
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
        description=(
            "`pending_consents` lista los códigos de los consentimientos obligatorios "
            "que faltan aceptar; mientras no esté vacía, las escrituras responden "
            "`403 CONSENT_REQUIRED`."
        ),
        responses={200: BuyerSessionResponseSerializer, **SESSION_ERRORS},
    )
    def get(self, request: Request) -> Response:
        return Response(BuyerSessionResponseSerializer(self.buyer_session).data)


class BuyerMetadataCatalogView(BuyerPortalView):
    """Catálogos de los formularios del comprador: la misma lógica de
    ``GET /metadata/catalogs/{code}``, limitada a ``BUYER_CATALOG_CODES``."""

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_metadata_catalogs_retrieve",
        summary="Valores activos y vigentes de un catálogo de los formularios del comprador",
        description=(
            f"{METADATA_CATALOG_DESCRIPTION} Misma respuesta que "
            "`GET /metadata/catalogs/{catalog_code}`, solo para los catálogos que usan los "
            "formularios del portal: "
            + ", ".join(f"`{code}`" for code in sorted(buyer_portal.BUYER_CATALOG_CODES))
            + ". Cualquier otro código responde `404`, igual que uno inexistente."
        ),
        parameters=METADATA_CATALOG_PARAMETERS,
        responses=METADATA_CATALOG_RESPONSES,
    )
    def get(self, request: Request, catalog_code: str) -> Response:
        return metadata_catalog_response(
            request, catalog_code, allowed=buyer_portal.BUYER_CATALOG_CODES
        )

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        # Sin datos personales: conserva el `private, no-cache` del catálogo, para que el
        # navegador revalide con `If-None-Match` en vez de descargarlo de nuevo.
        return super(BuyerPortalView, self).finalize_response(request, response, *args, **kwargs)


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
        parameters=[etag_response_headers(200)],
        responses={200: BuyerApplicationDetailSerializer, **NOT_FOUND, **SESSION_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        response = Response(BuyerApplicationDetailSerializer(application).data)
        return with_etag(response, application.version)


class BuyerConsentsView(BuyerPortalView):
    # Aceptar consentimientos no puede exigir consentimientos aceptados.
    permission_classes = [IsBuyerSession]

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_consents_list",
        summary="Consentimientos vigentes y su estado",
        description=(
            "La versión vigente de cada consentimiento, si es obligatorio para esta "
            "solicitud y la última acción del comprador sobre esa versión. "
            "`pending_required` son los obligatorios que faltan."
        ),
        responses={200: BuyerConsentListSerializer, **NOT_FOUND, **SESSION_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        states = consents.consent_states(self.buyer_session)
        body = {
            "items": states,
            "pending_required": [s.definition.code for s in states if s.is_missing],
        }
        return Response(BuyerConsentListSerializer(body).data)

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_consents_create",
        summary="Aceptar o retirar un consentimiento",
        description=(
            "Guarda la evidencia con la IP, el agente y la sesión. Repetir la última "
            "acción sobre la misma versión devuelve el registro existente (`200`). "
            "Retirar deja el consentimiento pendiente otra vez."
        ),
        request=BuyerConsentActionSerializer,
        responses={
            200: BuyerConsentRecordSerializer,
            201: BuyerConsentRecordSerializer,
            400: _error("VALIDATION_ERROR (también: definición inexistente)"),
            409: _error("CONSENT_NOT_ACCEPTED o APPLICATION_CLOSED"),
            422: _error("CONSENT_NOT_EFFECTIVE"),
            **NOT_FOUND,
            **SESSION_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        serializer = BuyerConsentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recorded = consents.record_consent(
            request=request,
            session=self.buyer_session,
            definition=serializer.validated_data["consent_definition_id"],
            action=serializer.validated_data["action"],
        )
        return Response(
            BuyerConsentRecordSerializer(recorded.record).data,
            status=status.HTTP_201_CREATED if recorded.created else status.HTTP_200_OK,
        )
