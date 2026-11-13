"""Inmueble, financiación, productos elegibles y desistimiento del comprador.

- ``GET``/``PUT /buyer/applications/{id}/property``
- ``GET``/``PUT /buyer/applications/{id}/financing``
- ``GET /buyer/applications/{id}/eligible-bank-products``
- ``POST /buyer/applications/{id}/withdrawals``

Las ediciones son las de los servicios internos, con la sesión como actor: mismas
reglas por finalidad y modalidad, ``If-Match`` y solo antes de `FILED`. El
desistimiento se admite también después de `FILED`.
"""

from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications import services
from apps.applications.concurrency import expected_version, with_etag
from apps.applications.models import FinancingPreference, Property
from apps.applications.serializers import (
    FinancingInputSerializer,
    StatusChangeSerializer,
    WithdrawalSerializer,
    property_model_values,
)
from apps.applications.views import IF_MATCH
from apps.identity.buyer_financing_serializers import (
    BuyerEligibleBankProductSerializer,
    BuyerPropertyInputSerializer,
)
from apps.identity.buyer_portal_serializers import (
    BuyerFinancingSerializer,
    BuyerPropertySerializer,
)
from apps.identity.buyer_portal_views import BUYER_PORTAL_TAG
from apps.identity.buyer_profile_views import (
    ETAG_NOTE,
    READ_ERRORS,
    VERSIONED_WRITE_ERRORS,
    WRITE_ERRORS,
    BuyerExpedienteView,
)
from config.openapi import etag_response_headers
from config.serializers import ErrorSerializer


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


class BuyerPropertyView(BuyerExpedienteView):
    def property_response(self, application_id: Any, **kwargs: Any) -> Response:
        prop = get_object_or_404(
            Property.objects.select_related(
                "project", "property_type_item", "condition_item", "city_item"
            ),
            application_id=application_id,
        )
        return self.etag(Response(BuyerPropertySerializer(prop).data, **kwargs))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_property_retrieve",
        summary="Inmueble de la solicitud",
        description=f"`404` si todavía no se registró. {ETAG_NOTE}",
        parameters=[etag_response_headers(200)],
        responses={200: BuyerPropertySerializer, **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        return self.property_response(application.pk)

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_property_update",
        summary="Crear o reemplazar los datos del inmueble",
        description=(
            "Mismas reglas por finalidad que el `PUT` interno. El proyecto y las notas "
            "del asesor no se envían y conservan su valor. Responde `201` si lo creó. "
            f"Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200, 201)],
        request=BuyerPropertyInputSerializer,
        responses={
            200: BuyerPropertySerializer,
            201: BuyerPropertySerializer,
            **VERSIONED_WRITE_ERRORS,
        },
    )
    def put(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        version = expected_version(request)
        serializer = BuyerPropertyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.put_property(
            self.buyer_session,
            application,
            expected_version=version,
            values=property_model_values(serializer.validated_data),
        )
        return self.property_response(
            application.pk, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class BuyerFinancingView(BuyerExpedienteView):
    def financing_response(self, application_id: Any, **kwargs: Any) -> Response:
        financing = get_object_or_404(
            FinancingPreference.objects.select_related(
                "application__bank_product__bank",
                "financing_mode_item",
                "currency_mode_item",
                "amortization_mode_item",
            ),
            application_id=application_id,
        )
        return self.etag(Response(BuyerFinancingSerializer(financing).data, **kwargs))

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_financing_retrieve",
        summary="Financiación y producto elegido",
        description=f"`404` si todavía no se registró. {ETAG_NOTE}",
        parameters=[etag_response_headers(200)],
        responses={200: BuyerFinancingSerializer, **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        return self.financing_response(application.pk)

    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_financing_update",
        summary="Crear o reemplazar la financiación y el producto",
        description=(
            "Mismas reglas que el `PUT` interno. Elegir un producto distinto guarda una "
            "evaluación de sus reglas, sin evaluador interno. Responde `201` si la creó. "
            f"Solo antes de `FILED`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH, etag_response_headers(200, 201)],
        request=FinancingInputSerializer,
        responses={
            200: BuyerFinancingSerializer,
            201: BuyerFinancingSerializer,
            **VERSIONED_WRITE_ERRORS,
        },
    )
    def put(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        version = expected_version(request)
        serializer = FinancingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = services.resolve_bank_product(serializer.validated_data["bank_product_id"])
        created = services.put_financing(
            self.buyer_session,
            application,
            expected_version=version,
            values=serializer.model_values(),
            product=product,
        )
        return self.financing_response(
            application.pk, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class BuyerEligibleBankProductsView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_eligible_bank_products",
        summary="Productos disponibles para la finalidad",
        description=(
            "Productos activos y vigentes que admiten la finalidad. `eligible` dice si los "
            "datos actuales cumplen las reglas bloqueantes del producto, sin el detalle "
            f"de las reglas. {ETAG_NOTE}"
        ),
        parameters=[etag_response_headers(200)],
        responses={200: BuyerEligibleBankProductSerializer(many=True), **READ_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        page = self.paginate_queryset(services.eligible_products_queryset(application)) or []
        evaluations = services.preview_products(application, page)
        data = BuyerEligibleBankProductSerializer(
            page, many=True, context={"evaluations": evaluations}
        ).data
        return self.etag(self.get_paginated_response(data))


class BuyerWithdrawalView(BuyerExpedienteView):
    @extend_schema(
        tags=[BUYER_PORTAL_TAG],
        operation_id="buyer_withdrawals_create",
        summary="Desistir de la solicitud",
        description=(
            "Pasa la solicitud a `WITHDRAWN` desde cualquier estado no terminal, también "
            "después de radicar. `reason_code` (catálogo `application_withdrawal_reason`) "
            "y `expected_version` son obligatorios. La sesión sigue viva para consultar. "
            f"{ETAG_NOTE}"
        ),
        request=WithdrawalSerializer,
        parameters=[etag_response_headers(200)],
        responses={
            200: StatusChangeSerializer,
            **WRITE_ERRORS,
            409: _error("STALE_VERSION, APPLICATION_CLOSED o INVALID_STATE_TRANSITION"),
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.ensure_session_application(application_id)
        serializer = WithdrawalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change = services.withdraw_application(
            self.buyer_session,
            application,
            expected_version=data["expected_version"],
            reason=data["reason_code"],
            comment=data["comment"],
        )
        response = Response(StatusChangeSerializer(change).data)
        return with_etag(response, change.application.version)
