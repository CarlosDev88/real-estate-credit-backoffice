"""Evidencias de consentimiento de una solicitud, para el backoffice (API §21.1).

``GET /applications/{id}/consents``, con el permiso ``consents.read`` (``ADMIN`` y
``ADVISOR``). El alcance es el de la solicitud; fuera de él se responde ``404``.
"""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.services import applications_visible_to
from apps.crm.serializers import UserRefSerializer
from apps.identity import consents
from apps.identity.models import ConsentAction, ConsentRecord, User
from apps.identity.permissions import HasPermissionCode
from config.serializers import ErrorSerializer

CONSENTS_TAG = "Consents"


class ConsentDefinitionRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    version = serializers.IntegerField()
    title = serializers.CharField()
    content_hash = serializers.CharField()


class ConsentClientRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class ConsentRecordSerializer(serializers.ModelSerializer):
    """Evidencia inmutable: qué versión, quién, cuándo, desde dónde y con qué sesión."""

    consent_definition = ConsentDefinitionRefSerializer(read_only=True)
    client = ConsentClientRefSerializer(read_only=True, allow_null=True)
    user = UserRefSerializer(read_only=True, allow_null=True)
    action = serializers.ChoiceField(choices=ConsentAction.choices, read_only=True)
    buyer_session_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = ConsentRecord
        fields = [
            "id",
            "consent_definition",
            "client",
            "user",
            "action",
            "ip_address",
            "user_agent_summary",
            "buyer_session_id",
            "created_at",
        ]
        read_only_fields = fields


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


class ApplicationConsentsView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions = {"GET": "consents.read"}

    @extend_schema(
        tags=[CONSENTS_TAG],
        operation_id="application_consents_list",
        summary="Evidencias de consentimiento de la solicitud",
        description="Aceptaciones y retiros, del más reciente al más antiguo.",
        responses={
            200: ConsentRecordSerializer(many=True),
            401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
            403: _error("PERMISSION_DENIED"),
            404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)"),
        },
    )
    def get(self, request: Request, application_id: Any) -> Response:
        user = cast(User, request.user)
        application = get_object_or_404(applications_visible_to(user), pk=application_id)
        page = self.paginate_queryset(consents.application_consent_records(application))
        return self.get_paginated_response(ConsentRecordSerializer(page, many=True).data)
