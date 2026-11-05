"""Endpoints de tipos y requisitos documentales (sección 23.4 de la API)."""

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

from apps.documents import services
from apps.documents.models import (
    DocumentRequirement,
    DocumentType,
    ParticipantRole,
    RequirementStatus,
)
from apps.documents.serializers import (
    ChecklistPreviewRequestSerializer,
    ChecklistPreviewResponseSerializer,
    DocumentRequirementCreateSerializer,
    DocumentRequirementSerializer,
    DocumentRequirementUpdateSerializer,
    DocumentTypeCreateSerializer,
    DocumentTypeSerializer,
    DocumentTypeUpdateSerializer,
)
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.partners.serializers import OptionalReasonSerializer
from config.filters import StrictOrderingFilter, parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

TYPES_TAG = "Document types"
REQUIREMENTS_TAG = "Document requirements"

# `/document-types` también usa `document_requirements.read`: solo ADMIN y ADVISOR.
READ = "document_requirements.read"
CREATE = "document_requirements.create"
UPDATE = "document_requirements.update"
PUBLISH = "document_requirements.publish"


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
# Tipos documentales
# --------------------------------------------------------------------------------------


def _get_type(document_type_id: Any) -> DocumentType:
    return get_object_or_404(services.document_types_queryset(), pk=document_type_id)


class DocumentTypeListView(PermissionCodeView):
    required_permissions = {"GET": READ, "POST": CREATE}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["name", "code", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self) -> QuerySet[DocumentType]:
        types = services.document_types_queryset()
        is_active = parse_bool_param(self.request, "is_active")
        if is_active is not None:
            types = types.filter(is_active=is_active)
        is_repeatable = parse_bool_param(self.request, "is_repeatable")
        if is_repeatable is not None:
            types = types.filter(is_repeatable=is_repeatable)
        return types

    @extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_list",
        summary="Listar tipos documentales",
        parameters=[
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("is_repeatable", OpenApiTypes.BOOL),
        ],
        responses={200: DocumentTypeSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(DocumentTypeSerializer(page, many=True).data)

    @extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_create",
        summary="Crear un tipo documental",
        request=DocumentTypeCreateSerializer,
        responses={201: DocumentTypeSerializer, 409: _error("DUPLICATE_CODE"), **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = DocumentTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_type = services.create_document_type(dict(serializer.validated_data))
        return Response(DocumentTypeSerializer(document_type).data, status=status.HTTP_201_CREATED)


class DocumentTypeDetailView(PermissionCodeView):
    required_permissions = {"GET": READ, "PATCH": UPDATE}

    @extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_retrieve",
        summary="Detalle y restricciones técnicas de un tipo documental",
        responses={200: DocumentTypeSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, document_type_id: Any) -> Response:
        return Response(DocumentTypeSerializer(_get_type(document_type_id)).data)

    @extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_partial_update",
        summary="Actualizar los metadatos de un tipo documental",
        request=DocumentTypeUpdateSerializer,
        responses={200: DocumentTypeSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def patch(self, request: Request, document_type_id: Any) -> Response:
        document_type = _get_type(document_type_id)
        serializer = DocumentTypeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_document_type(document_type, dict(serializer.validated_data))
        return Response(DocumentTypeSerializer(document_type).data)


class _DocumentTypeStatusView(PermissionCodeView):
    required_permissions = {"POST": PUBLISH}
    activate: bool

    def post(self, request: Request, document_type_id: Any) -> Response:
        document_type = _get_type(document_type_id)
        serializer = OptionalReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_document_type_active(
            document_type,
            active=self.activate,
            actor=self.actor,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(DocumentTypeSerializer(document_type).data)


_TYPE_STATUS_RESPONSES = {200: DocumentTypeSerializer, **NOT_FOUND, **COMMON_ERRORS}


@extend_schema_view(
    post=extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_activate",
        summary="Activar un tipo documental",
        request=OptionalReasonSerializer,
        responses=_TYPE_STATUS_RESPONSES,
    )
)
class DocumentTypeActivateView(_DocumentTypeStatusView):
    activate = True


@extend_schema_view(
    post=extend_schema(
        tags=[TYPES_TAG],
        operation_id="document_types_deactivate",
        summary="Desactivar un tipo documental",
        description=(
            "Sus requisitos dejan de aplicarse a casos nuevos y no se pueden publicar "
            "mientras el tipo esté inactivo. Los expedientes ya armados no cambian."
        ),
        request=OptionalReasonSerializer,
        responses=_TYPE_STATUS_RESPONSES,
    )
)
class DocumentTypeDeactivateView(_DocumentTypeStatusView):
    activate = False


# --------------------------------------------------------------------------------------
# Requisitos
# --------------------------------------------------------------------------------------


def _get_requirement(requirement_id: Any) -> DocumentRequirement:
    return get_object_or_404(services.requirements_queryset(), pk=requirement_id)


def _requirement_data(requirement_id: Any) -> dict[str, Any]:
    return DocumentRequirementSerializer(_get_requirement(requirement_id)).data


# (parámetro, lookup) de los filtros por código de catálogo.
_CATALOG_FILTERS = (
    ("purpose", "purpose_item__code"),
    ("employment_profile", "employment_profile_item__code"),
    ("property_condition", "property_condition_item__code"),
)


class DocumentRequirementListView(PermissionCodeView):
    required_permissions = {"GET": READ, "POST": CREATE}
    filter_backends = [StrictOrderingFilter]
    ordering_fields = ["sort_order", "version", "valid_from", "created_at", "updated_at"]
    ordering = ["sort_order", "document_type__code", "-version"]

    def get_queryset(self) -> QuerySet[DocumentRequirement]:
        requirements = services.requirements_queryset()
        params = self.request.query_params
        for param, lookup in (
            ("bank_id", "bank_product__bank_id"),
            ("bank_product_id", "bank_product_id"),
            ("document_type_id", "document_type_id"),
        ):
            value = parse_uuid_param(self.request, param)
            if value:
                requirements = requirements.filter(**{lookup: value})
        if parse_bool_param(self.request, "general"):
            requirements = requirements.filter(bank_product__isnull=True)
        requirement_status = _choice_param(self.request, "status", RequirementStatus.values)
        if requirement_status:
            requirements = requirements.filter(status=requirement_status)
        role = _choice_param(self.request, "participant_role", ParticipantRole.values)
        if role:
            requirements = requirements.filter(participant_role=role)
        for param, lookup in _CATALOG_FILTERS:
            if params.get(param):
                requirements = requirements.filter(**{lookup: params[param]})
        if params.get("document_type_code"):
            requirements = requirements.filter(document_type__code=params["document_type_code"])
        if params.get("alternative_group_code"):
            requirements = requirements.filter(
                alternative_group_code=params["alternative_group_code"]
            )
        return requirements

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_list",
        summary="Listar requisitos documentales y sus versiones",
        parameters=[
            OpenApiParameter("bank_id", OpenApiTypes.UUID),
            OpenApiParameter("bank_product_id", OpenApiTypes.UUID),
            OpenApiParameter(
                "general", OpenApiTypes.BOOL, description="Solo requisitos sin producto."
            ),
            OpenApiParameter("document_type_id", OpenApiTypes.UUID),
            OpenApiParameter("document_type_code", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR, enum=RequirementStatus.values),
            OpenApiParameter("participant_role", OpenApiTypes.STR, enum=ParticipantRole.values),
            OpenApiParameter("purpose", OpenApiTypes.STR, description="Código de `loan_purpose`."),
            OpenApiParameter(
                "employment_profile",
                OpenApiTypes.STR,
                description="Código de `employment_profile`.",
            ),
            OpenApiParameter(
                "property_condition",
                OpenApiTypes.STR,
                description="Código de `property_condition`.",
            ),
            OpenApiParameter("alternative_group_code", OpenApiTypes.STR),
        ],
        responses={200: DocumentRequirementSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(DocumentRequirementSerializer(page, many=True).data)

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_create",
        summary="Crear un requisito (versión 1, en borrador)",
        description=(
            "Un requisito lógico es su alcance: producto, tipo, finalidad, perfil laboral, "
            "rol del participante y condición del inmueble. Un campo vacío aplica a "
            "cualquier valor. Si el alcance ya existe responde 409 "
            "`REQUIREMENT_SCOPE_EXISTS` con el id de su última versión."
        ),
        request=DocumentRequirementCreateSerializer,
        responses={
            201: DocumentRequirementSerializer,
            409: _error("REQUIREMENT_SCOPE_EXISTS"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = DocumentRequirementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requirement = services.create_requirement(serializer.to_service_data())
        return Response(_requirement_data(requirement.pk), status=status.HTTP_201_CREATED)


class DocumentRequirementDetailView(PermissionCodeView):
    required_permissions = {"GET": READ, "PATCH": UPDATE}

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_retrieve",
        summary="Detalle y alcance de una versión de requisito",
        responses={200: DocumentRequirementSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, requirement_id: Any) -> Response:
        return Response(_requirement_data(requirement_id))

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_partial_update",
        summary="Editar el borrador o crear una versión nueva",
        description=(
            "Sobre un borrador (`DRAFT`) edita en el sitio y responde 200. Sobre una "
            "versión publicada (`ACTIVE` o `INACTIVE`) no la modifica: crea un borrador "
            "con `version + 1` y responde 201. Si el alcance ya tiene un borrador, "
            "responde 409 `REQUIREMENT_DRAFT_EXISTS` con su id en "
            "`details[0].resource_id`. El alcance no se edita."
        ),
        request=DocumentRequirementUpdateSerializer,
        responses={
            200: DocumentRequirementSerializer,
            201: DocumentRequirementSerializer,
            409: _error("REQUIREMENT_DRAFT_EXISTS"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, requirement_id: Any) -> Response:
        requirement = _get_requirement(requirement_id)
        serializer = DocumentRequirementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, created = services.update_requirement(requirement, serializer.to_service_data())
        return Response(
            _requirement_data(result.pk),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DocumentRequirementActivateView(PermissionCodeView):
    required_permissions = {"POST": PUBLISH}

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_activate",
        summary="Publicar una versión",
        description="La versión `ACTIVE` anterior del mismo alcance pasa a `INACTIVE`.",
        request=None,
        responses={
            200: DocumentRequirementSerializer,
            422: _error("DOCUMENT_TYPE_INACTIVE o REQUIREMENT_EXPIRED"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, requirement_id: Any) -> Response:
        services.activate_requirement(self.actor, _get_requirement(requirement_id))
        return Response(_requirement_data(requirement_id))


class DocumentRequirementDeactivateView(PermissionCodeView):
    required_permissions = {"POST": PUBLISH}

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_deactivate",
        summary="Dejar de pedir el documento en casos futuros",
        request=None,
        responses={
            200: DocumentRequirementSerializer,
            409: _error("INVALID_STATE_TRANSITION: un borrador no está publicado."),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, requirement_id: Any) -> Response:
        services.deactivate_requirement(self.actor, _get_requirement(requirement_id))
        return Response(_requirement_data(requirement_id))


class DocumentRequirementPreviewView(PermissionCodeView):
    required_permissions = {"POST": READ}

    @extend_schema(
        tags=[REQUIREMENTS_TAG],
        operation_id="document_requirements_preview",
        summary="Simular la lista documental de un caso de prueba",
        description=(
            "Aplica las versiones `ACTIVE`, vigentes en `at` y con tipo activo, sin tocar "
            "solicitudes. Los requisitos generales (sin producto) aplican a cualquier "
            "banco. Un campo vacío del requisito aplica a cualquier valor del caso; si el "
            "caso no trae un dato, solo aplican los requisitos que lo dejan vacío."
        ),
        request=ChecklistPreviewRequestSerializer,
        responses={200: ChecklistPreviewResponseSerializer, **COMMON_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = ChecklistPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = services.ChecklistCase(
            bank_product=data["bank_product_id"],
            purpose=data["purpose_code"],
            property_condition=data["property_condition_code"],
            at=data["at"],
            participants=[
                services.ParticipantCase(
                    role=participant["role"],
                    employment_profile=participant["employment_profile_code"],
                )
                for participant in data["participants"]
            ],
        )
        participants = services.preview_checklist(case)
        return Response(ChecklistPreviewResponseSerializer({"participants": participants}).data)
