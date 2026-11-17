"""Edición del expediente por el comprador: datos personales, perfiles e ingresos.

- ``GET``/``PATCH /buyer/applications/{id}/profile``
- ``GET /buyer/applications/{id}/participants``
- ``GET``/``PUT /buyer/participants/{participant_id}/financial-profile``
- ``POST /buyer/participants/{participant_id}/financial-profile/confirmation``
- ``GET``/``POST /buyer/financial-profiles/{id}/income-sources``
- ``PATCH``/``DELETE /buyer/income-sources/{id}``

Solo admiten recursos de la solicitud de la sesión; cualquier otro responde ``404``.
Toda respuesta lleva ``ETag`` con la versión de la solicitud. ``PUT``/``PATCH`` y la
confirmación exigen ``If-Match``.
"""

from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications import services
from apps.applications.concurrency import expected_version, with_etag
from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
)
from apps.applications.views import IF_MATCH
from apps.identity import buyer_editing
from apps.identity.buyer_portal_views import (
    BUYER_PORTAL_TAG,
    NOT_FOUND,
    SESSION_ERRORS,
    BuyerPortalView,
)
from apps.identity.buyer_profile_serializers import (
    BuyerFinancialProfileInputSerializer,
    BuyerFinancialProfileSerializer,
    BuyerIncomeSourceCreateSerializer,
    BuyerIncomeSourceSerializer,
    BuyerIncomeSourceUpdateSerializer,
    BuyerParticipantSummarySerializer,
    BuyerProfileSerializer,
    BuyerProfileUpdateSerializer,
)
from config.openapi import etag_response_headers
from config.serializers import ErrorSerializer


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


WRITE_ERRORS = {
    400: _error("VALIDATION_ERROR"),
    403: _error("CSRF_FAILED o CONSENT_REQUIRED"),
    409: _error(
        "STALE_VERSION, APPLICATION_NOT_EDITABLE (después de FILED), APPLICATION_CLOSED "
        "o PARTICIPANT_INACTIVE"
    ),
    401: SESSION_ERRORS[401],
    **NOT_FOUND,
}
VERSIONED_WRITE_ERRORS = {
    **WRITE_ERRORS,
    428: _error("PRECONDITION_REQUIRED (falta If-Match)"),
}
READ_ERRORS = {**NOT_FOUND, **SESSION_ERRORS}
ETAG_NOTE = "Responde `ETag` con la versión de la solicitud."


class BuyerExpedienteView(BuyerPortalView):
    def etag(self, response: Response) -> Response:
        """``ETag`` con la versión vigente, leída después del cambio."""
        version = CreditApplication.objects.values_list("version", flat=True).get(
            pk=self.buyer_session.application_id
        )
        return with_etag(response, version)

    def get_participant(self, participant_id: Any) -> ApplicationParticipant:
        return get_object_or_404(
            buyer_editing.buyer_participants(self.buyer_session), pk=participant_id
        )

    def get_profile(self, **lookup: Any) -> FinancialProfile:
        return get_object_or_404(
            buyer_editing.buyer_financial_profiles(self.buyer_session), **lookup
        )

    def get_income_source(self, source_id: Any) -> IncomeSource:
        return get_object_or_404(
            buyer_editing.buyer_income_sources(self.buyer_session), pk=source_id
        )

    def profile_response(self, participant: ApplicationParticipant, **kwargs: Any) -> Response:
        profile = self.get_profile(participant=participant)
        return self.etag(Response(BuyerFinancialProfileSerializer(profile).data, **kwargs))


# --- Datos personales -------------------------------------------------------------------


class BuyerProfileView(BuyerExpedienteView):
    def profile_body(self) -> dict[str, Any]:
        client = buyer_editing.buyer_client(self.buyer_session)
        context = {"addresses": buyer_editing.client_addresses(client)}
        return dict(BuyerProfileSerializer(client, context=context).data)

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_profile_retrieve",
        summary="Datos personales del titular",
        description=f"El documento va enmascarado. {ETAG_NOTE}",
        parameters=[etag_response_headers(200)],
        responses={200: BuyerProfileSerializer, **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        return self.etag(Response(self.profile_body()))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_profile_partial_update",
        summary="Actualizar los datos de contacto del titular",
        description=(
            "Admite `email`, `phone`, `birth_date` y `addresses`. Nombres y documento los "
            "corrige el asesor. `addresses` reemplaza la lista completa: con `id` se "
            "actualiza, sin `id` se crea y la que no llega se elimina; si ninguna es "
            f"principal, la primera lo es. Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200)],
        request=BuyerProfileUpdateSerializer,
        responses={200: BuyerProfileSerializer, **VERSIONED_WRITE_ERRORS},
    )
    def patch(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        version = expected_version(request)
        serializer = BuyerProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        buyer_editing.update_buyer_profile(
            self.buyer_session,
            expected_version=version,
            changes=serializer.contact_changes(),
            addresses=serializer.address_items(),
        )
        return self.etag(Response(self.profile_body()))


# --- Participantes y perfil financiero --------------------------------------------------


class BuyerParticipantsView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_participants_list",
        summary="Participantes activos de la solicitud",
        description=(
            "El titular y los co-solicitantes activos, incluidos los deudores solidarios. "
            f"El comprador edita el perfil financiero y los ingresos de todos. {ETAG_NOTE}"
        ),
        parameters=[etag_response_headers(200)],
        responses={200: BuyerParticipantSummarySerializer(many=True), **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        self.ensure_session_application(application_id)
        page = self.paginate_queryset(buyer_editing.buyer_participants(self.buyer_session))
        data = BuyerParticipantSummarySerializer(page, many=True).data
        return self.etag(self.get_paginated_response(data))


class BuyerFinancialProfileView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_financial_profile_retrieve",
        summary="Perfil financiero de un participante",
        description=f"`404` si el participante todavía no tiene perfil. {ETAG_NOTE}",
        parameters=[etag_response_headers(200)],
        responses={200: BuyerFinancialProfileSerializer, **READ_ERRORS},
    )
    def get(self, request: Request, participant_id: Any) -> Response:
        return self.profile_response(self.get_participant(participant_id))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_financial_profile_update",
        summary="Crear o reemplazar el perfil financiero",
        description=(
            "Reemplazo completo, con las mismas reglas que el `PUT` interno. Un cambio "
            "real limpia `data_confirmed_at`. Responde `201` si lo creó. Solo antes de "
            f"`FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200, 201)],
        request=BuyerFinancialProfileInputSerializer,
        responses={
            200: BuyerFinancialProfileSerializer,
            201: BuyerFinancialProfileSerializer,
            **VERSIONED_WRITE_ERRORS,
        },
    )
    def put(self, request: Request, participant_id: Any) -> Response:
        participant = self.get_participant(participant_id)
        version = expected_version(request)
        serializer = BuyerFinancialProfileInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.put_financial_profile(
            self.buyer_session,
            participant,
            expected_version=version,
            values=serializer.model_values(),
        )
        return self.profile_response(
            participant, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class BuyerFinancialProfileConfirmationView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_financial_profile_confirm",
        summary="Confirmar el perfil financiero",
        description=(
            "Fija `data_confirmed_at` y aumenta la versión. Exige `If-Match` y un perfil "
            "existente (`404` si falta). Confirmar un perfil ya confirmado no cambia "
            f"nada. Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200)],
        request=None,
        responses={200: BuyerFinancialProfileSerializer, **VERSIONED_WRITE_ERRORS},
    )
    def post(self, request: Request, participant_id: Any) -> Response:
        participant = self.get_participant(participant_id)
        version = expected_version(request)
        services.confirm_financial_profile(
            self.buyer_session, participant, expected_version=version
        )
        return self.profile_response(participant)


# --- Fuentes de ingreso -----------------------------------------------------------------


class BuyerIncomeSourcesView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_income_sources_list",
        summary="Fuentes de ingreso del perfil",
        description=f"La principal primero. {ETAG_NOTE}",
        parameters=[etag_response_headers(200)],
        responses={200: BuyerIncomeSourceSerializer(many=True), **READ_ERRORS},
    )
    def get(self, request: Request, profile_id: Any) -> Response:
        profile = self.get_profile(pk=profile_id)
        sources = profile.income_sources.select_related("source_type_item")
        page = self.paginate_queryset(sources)
        data = BuyerIncomeSourceSerializer(page, many=True).data
        return self.etag(self.get_paginated_response(data))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_income_sources_create",
        summary="Agregar una fuente de ingreso",
        description=(
            "No exige `If-Match`, pero aumenta la versión y limpia `data_confirmed_at` "
            f"del perfil. Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        request=BuyerIncomeSourceCreateSerializer,
        parameters=[etag_response_headers(201)],
        responses={201: BuyerIncomeSourceSerializer, **WRITE_ERRORS},
    )
    def post(self, request: Request, profile_id: Any) -> Response:
        profile = self.get_profile(pk=profile_id)
        serializer = BuyerIncomeSourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = services.add_income_source(self.buyer_session, profile, serializer.model_values())
        body = BuyerIncomeSourceSerializer(self.get_income_source(source.pk)).data
        return self.etag(Response(body, status=status.HTTP_201_CREATED))


class BuyerIncomeSourceDetailView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_income_sources_partial_update",
        summary="Editar una fuente de ingreso",
        description=(
            "Marcarla como principal desmarca la anterior. Un cambio real limpia "
            f"`data_confirmed_at` del perfil. Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200)],
        request=BuyerIncomeSourceUpdateSerializer,
        responses={200: BuyerIncomeSourceSerializer, **VERSIONED_WRITE_ERRORS},
    )
    def patch(self, request: Request, income_source_id: Any) -> Response:
        source = self.get_income_source(income_source_id)
        version = expected_version(request)
        serializer = BuyerIncomeSourceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_income_source(
            self.buyer_session,
            source,
            expected_version=version,
            changes=serializer.model_values(),
        )
        body = BuyerIncomeSourceSerializer(self.get_income_source(income_source_id)).data
        return self.etag(Response(body))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_income_sources_destroy",
        summary="Eliminar una fuente de ingreso",
        description=(
            "No exige `If-Match`, pero aumenta la versión y limpia `data_confirmed_at` "
            f"del perfil. Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[etag_response_headers(204)],
        responses={204: OpenApiResponse(description="Eliminada."), **WRITE_ERRORS},
    )
    def delete(self, request: Request, income_source_id: Any) -> Response:
        source = self.get_income_source(income_source_id)
        services.delete_income_source(self.buyer_session, source)
        return self.etag(Response(status=status.HTTP_204_NO_CONTENT))
