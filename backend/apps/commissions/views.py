"""Comisiones (API §23.6). Parte 1: planes por producto."""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.concurrency import expected_version, with_etag
from apps.audit.actions import AuditAction
from apps.commissions import plans
from apps.commissions.models import CommissionPlan
from apps.commissions.serializers import (
    CommissionPlanCloseSerializer,
    CommissionPlanCreateSerializer,
    CommissionPlanSerializer,
    CommissionPlanUpdateSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import parse_uuid_param
from config.openapi import etag_response_headers
from config.serializers import ErrorSerializer

PLANS_TAG = "Commission plans"

READ_PLANS = "commission_plans.read"
MANAGE_PLANS = "commission_plans.manage"

PLAN_ETAG = 'Versión del plan, por ejemplo `"2"`. Se reenvía en `If-Match` al editarlo.'


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND")}
VALIDATION = {400: _error("VALIDATION_ERROR")}


class PermissionCodeView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)


def _plan_response(plan: CommissionPlan, status_code: int = status.HTTP_200_OK) -> Response:
    fresh = plans.plans_queryset().get(pk=plan.pk)
    response = Response(CommissionPlanSerializer(fresh).data, status=status_code)
    return with_etag(response, fresh.version)


def _get_plan(plan_id: Any) -> CommissionPlan:
    return get_object_or_404(plans.plans_queryset(), pk=plan_id)


class CommissionPlanListView(PermissionCodeView):
    # Auditoría (módulo 14, apps/audit/hooks.py).
    audit_actions = {"POST": AuditAction.COMMISSION_PLAN_CHANGED}
    audit_resource_type = "commission_plans"
    required_permissions = {"GET": READ_PLANS, "POST": MANAGE_PLANS}

    @extend_schema(
        tags=[PLANS_TAG],
        operation_id="commission_plans_list",
        summary="Planes de comisión",
        description=(
            "Por producto y del más reciente al más antiguo. `vigente_en` deja los planes "
            "vigentes en esa fecha (`valid_from` <= fecha < `valid_until`)."
        ),
        parameters=[
            OpenApiParameter("bank_product_id", OpenApiTypes.UUID),
            OpenApiParameter("vigente_en", OpenApiTypes.DATE),
        ],
        responses={200: CommissionPlanSerializer(many=True), **VALIDATION, **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        queryset = plans.plans_queryset()
        product_id = parse_uuid_param(request, "bank_product_id")
        if product_id:
            queryset = queryset.filter(bank_product_id=product_id)
        raw_day = request.query_params.get("vigente_en")
        if raw_day:
            try:
                day = parse_date(raw_day)
            except ValueError:
                day = None
            if day is None:
                raise ValidationError({"vigente_en": ["Debe ser una fecha (AAAA-MM-DD)."]})
            queryset = queryset.filter(plans.valid_on(day))
        page = self.paginate_queryset(queryset.order_by("bank_product__name", "-valid_from"))
        return self.get_paginated_response(CommissionPlanSerializer(page, many=True).data)

    @extend_schema(
        tags=[PLANS_TAG],
        operation_id="commission_plans_create",
        summary="Crear un plan de comisión",
        description=(
            "`rate_pct` mayor que 0 y como mucho 100. `advisor_share_pct` + "
            "`broker_share_pct` = 100, y el asesor lleva la porción mayor. La vigencia no "
            "puede solaparse con otro plan del mismo producto (`409 COMMISSION_PLAN_OVERLAP`)."
        ),
        request=CommissionPlanCreateSerializer,
        parameters=[etag_response_headers(201, description=PLAN_ETAG)],
        responses={
            201: CommissionPlanSerializer,
            **VALIDATION,
            409: _error("COMMISSION_PLAN_OVERLAP"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CommissionPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = plans.create_plan(self.actor, dict(serializer.validated_data))
        return _plan_response(plan, status.HTTP_201_CREATED)


class CommissionPlanDetailView(PermissionCodeView):
    # Auditoría (módulo 14, apps/audit/hooks.py).
    audit_actions = {"PATCH": AuditAction.COMMISSION_PLAN_CHANGED}
    audit_resource_type = "commission_plans"
    required_permissions = {"GET": READ_PLANS, "PATCH": MANAGE_PLANS}

    @extend_schema(
        tags=[PLANS_TAG],
        operation_id="commission_plans_retrieve",
        summary="Detalle de un plan de comisión",
        parameters=[etag_response_headers(200, description=PLAN_ETAG)],
        responses={200: CommissionPlanSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, plan_id: Any) -> Response:
        return _plan_response(_get_plan(plan_id))

    @extend_schema(
        tags=[PLANS_TAG],
        operation_id="commission_plans_partial_update",
        summary="Editar un plan que ninguna liquidación usó",
        description=(
            "Exige `If-Match` con la versión del plan (`428` sin ella, `409 STALE_VERSION` "
            "con otra). Un plan en uso no se edita (`409 COMMISSION_PLAN_IN_USE`): se cierra "
            "y se crea uno nuevo. El producto no cambia."
        ),
        request=CommissionPlanUpdateSerializer,
        parameters=[etag_response_headers(200, description=PLAN_ETAG)],
        responses={
            200: CommissionPlanSerializer,
            **VALIDATION,
            **NOT_FOUND,
            409: _error("STALE_VERSION, COMMISSION_PLAN_IN_USE o COMMISSION_PLAN_OVERLAP"),
            428: _error("PRECONDITION_REQUIRED"),
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, plan_id: Any) -> Response:
        plan = _get_plan(plan_id)
        version = expected_version(request)
        serializer = CommissionPlanUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = plans.update_plan(plan, dict(serializer.validated_data), expected_version=version)
        return _plan_response(updated)


class CommissionPlanCloseView(PermissionCodeView):
    # Auditoría (módulo 14, apps/audit/hooks.py).
    audit_actions = {"POST": AuditAction.COMMISSION_PLAN_CHANGED}
    audit_resource_type = "commission_plans"
    required_permissions = {"POST": MANAGE_PLANS}

    @extend_schema(
        tags=[PLANS_TAG],
        operation_id="commission_plans_close",
        summary="Cerrar un plan de comisión",
        description=(
            "Fija `valid_until` (exclusivo). Se permite también en un plan en uso. Solo "
            "adelanta el fin: un plan ya cerrado no se alarga."
        ),
        request=CommissionPlanCloseSerializer,
        parameters=[etag_response_headers(200, description=PLAN_ETAG)],
        responses={200: CommissionPlanSerializer, **VALIDATION, **NOT_FOUND, **COMMON_ERRORS},
    )
    def post(self, request: Request, plan_id: Any) -> Response:
        plan = _get_plan(plan_id)
        serializer = CommissionPlanCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _plan_response(plans.close_plan(plan, serializer.validated_data["valid_until"]))
