"""Endpoints de bancos y productos (sección 23.2) y de reglas operativas (sección 23.3)."""

from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.banking import services
from apps.banking.models import (
    Bank,
    BankPolicyRule,
    BankProduct,
    BankStatus,
    RuleSeverity,
    RuleStatus,
)
from apps.banking.rule_engine import Outcome
from apps.banking.serializers import (
    BankCreateSerializer,
    BankDetailSerializer,
    BankPolicyRuleCreateSerializer,
    BankPolicyRuleSerializer,
    BankPolicyRuleUpdateSerializer,
    BankProductCreateSerializer,
    BankProductSerializer,
    BankProductUpdateSerializer,
    BankSerializer,
    BankUpdateSerializer,
    ProductPurposesSerializer,
    RuleTestRequestSerializer,
    RuleTestResponseSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.partners.serializers import OptionalReasonSerializer
from config.filters import StrictOrderingFilter, parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

BANKS_TAG = "Banks"
RULES_TAG = "Bank policy rules"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND")}


class PermissionCodeView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)


def _choice_param(request: Request, name: str, choices: list[str]) -> str | None:
    value = request.query_params.get(name)
    if not value:
        return None
    if value not in choices:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return value


# --------------------------------------------------------------------------------------
# Bancos
# --------------------------------------------------------------------------------------


def _get_bank(bank_id: Any) -> Bank:
    return get_object_or_404(services.banks_queryset(), pk=bank_id)


class BankListView(PermissionCodeView):
    required_permissions = {"GET": "banks.read", "POST": "banks.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "name", "tax_id"]
    ordering_fields = ["name", "code", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self) -> QuerySet[Bank]:
        banks = services.banks_queryset()
        bank_status = _choice_param(self.request, "status", BankStatus.values)
        if bank_status:
            banks = banks.filter(status=bank_status)
        return banks

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_list",
        summary="Listar bancos",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=BankStatus.values)],
        responses={200: BankSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(BankSerializer(page, many=True).data)

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_create",
        summary="Crear un banco",
        request=BankCreateSerializer,
        responses={201: BankSerializer, 409: _error("DUPLICATE_CODE"), **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = BankCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bank = services.create_bank(dict(serializer.validated_data))
        return Response(BankSerializer(bank).data, status=status.HTTP_201_CREATED)


class BankDetailView(PermissionCodeView):
    required_permissions = {"GET": "banks.read", "PATCH": "banks.update"}

    def _detail(self, bank_id: Any) -> dict[str, Any]:
        bank = get_object_or_404(services.banks_queryset().prefetch_related("products"), pk=bank_id)
        return BankDetailSerializer(bank).data

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_retrieve",
        summary="Detalle del banco y sus productos",
        responses={200: BankDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, bank_id: Any) -> Response:
        return Response(self._detail(bank_id))

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_partial_update",
        summary="Actualizar datos operativos del banco",
        request=BankUpdateSerializer,
        responses={200: BankDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, bank_id: Any) -> Response:
        bank = _get_bank(bank_id)
        serializer = BankUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_bank(bank, dict(serializer.validated_data))
        return Response(self._detail(bank_id))


class _BankStatusView(PermissionCodeView):
    required_permissions = {"POST": "banks.update"}
    activate: bool

    def post(self, request: Request, bank_id: Any) -> Response:
        bank = _get_bank(bank_id)
        serializer = OptionalReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_bank_status(
            bank,
            active=self.activate,
            actor=self.actor,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(BankSerializer(bank).data)


_BANK_STATUS_RESPONSES = {200: BankSerializer, **NOT_FOUND, **COMMON_ERRORS}


@extend_schema_view(
    post=extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_activate",
        summary="Habilitar un banco para nuevas solicitudes",
        request=OptionalReasonSerializer,
        responses=_BANK_STATUS_RESPONSES,
    )
)
class BankActivateView(_BankStatusView):
    activate = True


@extend_schema_view(
    post=extend_schema(
        tags=[BANKS_TAG],
        operation_id="banks_deactivate",
        summary="Deshabilitar un banco sin alterar el historial",
        request=OptionalReasonSerializer,
        responses=_BANK_STATUS_RESPONSES,
    )
)
class BankDeactivateView(_BankStatusView):
    activate = False


# --------------------------------------------------------------------------------------
# Productos
# --------------------------------------------------------------------------------------


def _get_product(product_id: Any) -> BankProduct:
    return get_object_or_404(services.products_queryset(), pk=product_id)


class BankProductListView(PermissionCodeView):
    required_permissions = {"GET": "banks.read", "POST": "banks.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "name", "bank__name", "bank__code"]
    ordering_fields = ["name", "code", "valid_from", "created_at", "updated_at"]
    ordering = ["bank__name", "name"]

    def get_queryset(self) -> QuerySet[BankProduct]:
        params = self.request.query_params
        if parse_bool_param(self.request, "available"):
            products = services.available_products()
        else:
            products = services.products_queryset()
        bank_id = parse_uuid_param(self.request, "bank_id")
        if bank_id:
            products = products.filter(bank_id=bank_id)
        product_status = _choice_param(self.request, "status", BankStatus.values)
        if product_status:
            products = products.filter(status=product_status)
        if params.get("product_type"):
            products = products.filter(product_type_item__code=params["product_type"])
        if params.get("purpose"):
            products = products.filter(
                purposes__purpose_item__code=params["purpose"], purposes__is_active=True
            ).distinct()
        return products

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_list",
        summary="Listar productos de crédito",
        parameters=[
            OpenApiParameter("bank_id", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR, enum=BankStatus.values),
            OpenApiParameter(
                "product_type", OpenApiTypes.STR, description="Código de `bank_product_type`."
            ),
            OpenApiParameter("purpose", OpenApiTypes.STR, description="Código de `loan_purpose`."),
            OpenApiParameter(
                "available",
                OpenApiTypes.BOOL,
                description="Solo productos elegibles hoy: banco y producto activos y vigentes.",
            ),
        ],
        responses={200: BankProductSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(BankProductSerializer(page, many=True).data)

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_create",
        summary="Crear un producto de crédito",
        request=BankProductCreateSerializer,
        responses={201: BankProductSerializer, 409: _error("DUPLICATE_CODE"), **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = BankProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_service_data()
        data.setdefault("valid_from", services.today())
        product = services.create_product(data)
        return Response(
            BankProductSerializer(_get_product(product.pk)).data, status=status.HTTP_201_CREATED
        )


class BankProductDetailView(PermissionCodeView):
    required_permissions = {"GET": "banks.read", "PATCH": "banks.update"}

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_retrieve",
        summary="Condiciones y finalidades de un producto",
        responses={200: BankProductSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, product_id: Any) -> Response:
        return Response(BankProductSerializer(_get_product(product_id)).data)

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_partial_update",
        summary="Actualizar un producto",
        request=BankProductUpdateSerializer,
        responses={200: BankProductSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, product_id: Any) -> Response:
        product = _get_product(product_id)
        serializer = BankProductUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_product(product, serializer.to_service_data())
        return Response(BankProductSerializer(_get_product(product_id)).data)


class _ProductStatusView(PermissionCodeView):
    required_permissions = {"POST": "banks.update"}
    activate: bool

    def post(self, request: Request, product_id: Any) -> Response:
        product = _get_product(product_id)
        serializer = OptionalReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_product_status(
            product,
            active=self.activate,
            actor=self.actor,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(BankProductSerializer(product).data)


_PRODUCT_STATUS_RESPONSES = {200: BankProductSerializer, **NOT_FOUND, **COMMON_ERRORS}


@extend_schema_view(
    post=extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_activate",
        summary="Activar un producto",
        request=OptionalReasonSerializer,
        responses=_PRODUCT_STATUS_RESPONSES,
    )
)
class BankProductActivateView(_ProductStatusView):
    activate = True


@extend_schema_view(
    post=extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_deactivate",
        summary="Desactivar un producto",
        request=OptionalReasonSerializer,
        responses=_PRODUCT_STATUS_RESPONSES,
    )
)
class BankProductDeactivateView(_ProductStatusView):
    activate = False


class BankProductPurposesView(PermissionCodeView):
    required_permissions = {"PUT": "banks.update"}

    @extend_schema(
        tags=[BANKS_TAG],
        operation_id="bank_products_purposes_update",
        summary="Definir las finalidades admitidas (reemplaza la lista)",
        description="Las finalidades que salen de la lista se desactivan, no se borran.",
        request=ProductPurposesSerializer,
        responses={200: BankProductSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def put(self, request: Request, product_id: Any) -> Response:
        product = _get_product(product_id)
        serializer = ProductPurposesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_product_purposes(product, serializer.validated_data["purpose_codes"])
        return Response(BankProductSerializer(_get_product(product_id)).data)


# --------------------------------------------------------------------------------------
# Reglas operativas
# --------------------------------------------------------------------------------------


def _get_rule(rule_id: Any) -> BankPolicyRule:
    return get_object_or_404(services.rules_queryset(), pk=rule_id)


def _rule_data(rule_id: Any) -> dict[str, Any]:
    return BankPolicyRuleSerializer(_get_rule(rule_id)).data


class BankPolicyRuleListView(PermissionCodeView):
    required_permissions = {"GET": "bank_rules.read", "POST": "bank_rules.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "message"]
    ordering_fields = ["code", "version", "valid_from", "created_at", "updated_at"]
    ordering = ["code", "-version"]

    def get_queryset(self) -> QuerySet[BankPolicyRule]:
        rules = services.rules_queryset()
        params = self.request.query_params
        for param, lookup in (
            ("bank_id", "bank_product__bank_id"),
            ("bank_product_id", "bank_product_id"),
        ):
            value = parse_uuid_param(self.request, param)
            if value:
                rules = rules.filter(**{lookup: value})
        rule_status = _choice_param(self.request, "status", RuleStatus.values)
        if rule_status:
            rules = rules.filter(status=rule_status)
        severity = _choice_param(self.request, "severity", RuleSeverity.values)
        if severity:
            rules = rules.filter(severity=severity)
        if params.get("code"):
            rules = rules.filter(code=params["code"])
        if params.get("purpose"):
            rules = rules.filter(purpose_item__code=params["purpose"])
        return rules

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_list",
        summary="Listar reglas y sus versiones",
        parameters=[
            OpenApiParameter("bank_id", OpenApiTypes.UUID),
            OpenApiParameter("bank_product_id", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR, enum=RuleStatus.values),
            OpenApiParameter("severity", OpenApiTypes.STR, enum=RuleSeverity.values),
            OpenApiParameter("code", OpenApiTypes.STR),
            OpenApiParameter("purpose", OpenApiTypes.STR, description="Código de `loan_purpose`."),
        ],
        responses={200: BankPolicyRuleSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(BankPolicyRuleSerializer(page, many=True).data)

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_create",
        summary="Crear una regla (versión 1, en borrador)",
        request=BankPolicyRuleCreateSerializer,
        responses={
            201: BankPolicyRuleSerializer,
            409: _error("DUPLICATE_CODE: el código ya existe en el producto."),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = BankPolicyRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = services.create_rule(self.actor, serializer.to_service_data())
        return Response(_rule_data(rule.pk), status=status.HTTP_201_CREATED)


class BankPolicyRuleDetailView(PermissionCodeView):
    required_permissions = {"GET": "bank_rules.read", "PATCH": "bank_rules.update"}

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_retrieve",
        summary="Detalle de una versión de regla",
        responses={200: BankPolicyRuleSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, rule_id: Any) -> Response:
        return Response(_rule_data(rule_id))

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_partial_update",
        summary="Editar el borrador o crear una versión nueva",
        description=(
            "Sobre un borrador (`DRAFT`) edita en el sitio y responde 200. Sobre una "
            "versión publicada (`ACTIVE` o `INACTIVE`) no la modifica: crea un borrador "
            "con `version + 1` y responde 201. Si la regla ya tiene un borrador, responde "
            "409 `RULE_DRAFT_EXISTS` con su id en `details[0].resource_id`."
        ),
        request=BankPolicyRuleUpdateSerializer,
        responses={
            200: BankPolicyRuleSerializer,
            201: BankPolicyRuleSerializer,
            409: _error("RULE_DRAFT_EXISTS"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, rule_id: Any) -> Response:
        rule = _get_rule(rule_id)
        serializer = BankPolicyRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, created = services.update_rule(self.actor, rule, serializer.to_service_data())
        return Response(
            _rule_data(result.pk),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BankPolicyRuleActivateView(PermissionCodeView):
    required_permissions = {"POST": "bank_rules.publish"}

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_activate",
        summary="Publicar una versión",
        description="La versión `ACTIVE` anterior de la misma regla pasa a `INACTIVE`.",
        request=None,
        responses={
            200: BankPolicyRuleSerializer,
            422: _error("RULE_CONDITION_INVALID o RULE_EXPIRED"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, rule_id: Any) -> Response:
        services.activate_rule(self.actor, _get_rule(rule_id))
        return Response(_rule_data(rule_id))


class BankPolicyRuleDeactivateView(PermissionCodeView):
    required_permissions = {"POST": "bank_rules.publish"}

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_deactivate",
        summary="Detener la aplicación futura de una versión publicada",
        request=None,
        responses={
            200: BankPolicyRuleSerializer,
            409: _error("INVALID_STATE_TRANSITION: un borrador no está publicado."),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, rule_id: Any) -> Response:
        services.deactivate_rule(self.actor, _get_rule(rule_id))
        return Response(_rule_data(rule_id))


class BankPolicyRuleTestView(PermissionCodeView):
    required_permissions = {"POST": "bank_rules.update"}

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_test",
        summary="Ejecutar casos de prueba sin afectar solicitudes",
        description=(
            "Cada caso trae un `context` con los campos de la lista blanca. El resultado "
            "es `PASSED`, `FAILED` o `MISSING_DATA` (con `unresolved_fields`)."
        ),
        request=RuleTestRequestSerializer,
        responses={
            200: RuleTestResponseSerializer,
            422: _error("RULE_CONDITION_INVALID"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, rule_id: Any) -> Response:
        rule = _get_rule(rule_id)
        serializer = RuleTestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cases = [
            services.RuleTestCase(
                name=case["name"],
                context=case["context"],
                expected=Outcome(case["expected"]) if case["expected"] else None,
            )
            for case in serializer.validated_data["cases"]
        ]
        results = services.run_rule_tests(rule, cases)
        return Response(RuleTestResponseSerializer({"rule": rule, "results": results}).data)


class BankPolicyRuleVersionsView(PermissionCodeView):
    required_permissions = {"GET": "bank_rules.read"}

    @extend_schema(
        tags=[RULES_TAG],
        operation_id="bank_policy_rules_versions_list",
        summary="Historial de versiones de la regla",
        responses={200: BankPolicyRuleSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, rule_id: Any) -> Response:
        versions = services.rule_versions(_get_rule(rule_id)).order_by("-version")
        page = self.paginate_queryset(versions)
        return self.get_paginated_response(BankPolicyRuleSerializer(page, many=True).data)
