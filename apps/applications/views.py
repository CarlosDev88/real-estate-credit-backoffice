"""Endpoints de solicitudes de crédito (API §16), sus participantes, perfiles financieros
e ingresos (§17) y `GET /clients/{id}/applications` (§13)."""

from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications import services
from apps.applications.concurrency import IF_MATCH_HEADER, expected_version, with_etag
from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
)
from apps.applications.serializers import (
    ApplicationCreateSerializer,
    ApplicationDetailSerializer,
    ApplicationParticipantSerializer,
    ApplicationSerializer,
    ApplicationSummarySerializer,
    ApplicationUpdateSerializer,
    AssignmentCreateSerializer,
    FinancialProfileInputSerializer,
    FinancialProfileSerializer,
    IncomeSourceCreateSerializer,
    IncomeSourceSerializer,
    IncomeSourceUpdateSerializer,
    ParticipantCreateSerializer,
    ParticipantUpdateSerializer,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.services import CrmScope, clients_visible_to, resolve_visible_client
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from config.filters import StrictOrderingFilter, parse_bool_param, parse_uuid_param
from config.serializers import ErrorSerializer

APPLICATIONS_TAG = "Applications"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}
IF_MATCH = OpenApiParameter(
    IF_MATCH_HEADER,
    OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description='Versión de la solicitud que se editó, tal como llegó en `ETag` (`"3"`).',
)
STATUS_PARAM = OpenApiParameter("status", OpenApiTypes.STR, enum=ApplicationStatus.values)


class ApplicationView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    @property
    def scope(self) -> CrmScope:
        if not hasattr(self, "_scope"):
            self._scope = services.get_application_scope(self.actor)
        return self._scope

    def get_application(self, application_id: Any) -> CreditApplication:
        return get_object_or_404(services.applications_visible_to(self.actor), pk=application_id)

    def list_serializer_class(self) -> type[ApplicationSerializer | ApplicationSummarySerializer]:
        return ApplicationSummarySerializer if self.scope.is_restricted else ApplicationSerializer


def _choice_param(request: Request, name: str, choices: list[str]) -> str | None:
    value = request.query_params.get(name)
    if not value:
        return None
    if value not in choices:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(choices)}."]})
    return value


def _detail_response(view: ApplicationView, application_id: Any, **kwargs: Any) -> Response:
    """Detalle según el actor: el broker solo recibe el resumen."""
    application = view.get_application(application_id)
    serializer_class = (
        ApplicationSummarySerializer if view.scope.is_restricted else ApplicationDetailSerializer
    )
    return with_etag(Response(serializer_class(application).data, **kwargs), application.version)


class ApplicationListView(ApplicationView):
    required_permissions = {"GET": "applications.read", "POST": "applications.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = [
        "code",
        "opportunity__client__first_names",
        "opportunity__client__last_names",
        "opportunity__client__document_number",
    ]
    ordering_fields = ["created_at", "updated_at", "status", "code"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[CreditApplication]:
        applications = services.applications_visible_to(self.actor)
        application_status = _choice_param(self.request, "status", ApplicationStatus.values)
        if application_status:
            applications = applications.filter(status=application_status)
        for param, field in (
            ("bank_id", "bank_product__bank_id"),
            ("product_id", "bank_product_id"),
            ("advisor_id", "assigned_advisor_id"),
            ("project_id", "financed_property__project_id"),
        ):
            value = parse_uuid_param(self.request, param)
            if value:
                applications = applications.filter(**{field: value})
        for param, field in (
            ("purpose", "purpose_item__code"),
            ("origin", "opportunity__origin_item__code"),
        ):
            code = self.request.query_params.get(param)
            if code:
                applications = applications.filter(**{field: code})
        return applications

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_list",
        summary="Solicitudes según el alcance",
        description=(
            "El administrador ve todas, el asesor las asignadas y el broker el resumen de "
            "las solicitudes de las oportunidades que originó."
        ),
        parameters=[
            STATUS_PARAM,
            OpenApiParameter("bank_id", OpenApiTypes.UUID),
            OpenApiParameter("product_id", OpenApiTypes.UUID),
            OpenApiParameter("purpose", OpenApiTypes.STR, description="Código `loan_purpose`."),
            OpenApiParameter("advisor_id", OpenApiTypes.UUID),
            OpenApiParameter("project_id", OpenApiTypes.UUID),
            OpenApiParameter("origin", OpenApiTypes.STR, description="Código `lead_origin`."),
        ],
        responses={200: ApplicationSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer_class = self.list_serializer_class()
        return self.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_create",
        summary="Crear una solicitud DRAFT a partir de una oportunidad",
        description=(
            "Convierte la oportunidad (`CONVERTED`) en la misma transacción y crea el "
            "titular, el inmueble inicial, la asignación y el primer registro del "
            "historial. Sin `assigned_advisor_id` usa el asesor de la oportunidad. "
            "Una oportunidad ya convertida admite otro intento solo si los anteriores "
            "terminaron en `REJECTED`, `WITHDRAWN` o `CANCELLED`."
        ),
        request=ApplicationCreateSerializer,
        responses={
            201: ApplicationDetailSerializer,
            409: _error("APPLICATION_ALREADY_OPEN o INVALID_STATE_TRANSITION"),
            422: _error("ADVISOR_NOT_ELIGIBLE o PROJECT_NOT_ACTIVE"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        opportunity = services.resolve_visible_opportunity(self.actor, data["opportunity_id"])
        property_data = serializer.property_values()
        if property_data is not None:
            property_data["project"] = services.resolve_property_project(
                self.actor, data["project_id"]
            )
        application = services.create_application(
            self.actor,
            opportunity=opportunity,
            purpose=data["purpose_code"],
            advisor=data["assigned_advisor_id"],
            property_data=property_data,
        )
        # Se responde con lo creado aunque quien lo creó no quede como asesor asignado.
        created = services.applications_queryset().get(pk=application.pk)
        return with_etag(
            Response(ApplicationDetailSerializer(created).data, status=status.HTTP_201_CREATED),
            created.version,
        )


class ApplicationDetailView(ApplicationView):
    required_permissions = {"GET": "applications.read", "PATCH": "applications.update"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_retrieve",
        summary="Expediente según el rol",
        description=(
            "Responde `ETag` con la versión, que se reenvía en `If-Match` al editar. El "
            "broker recibe solo el resumen."
        ),
        responses={200: ApplicationDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        return _detail_response(self, application_id)

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_partial_update",
        summary="Cambiar la finalidad o el producto antes de radicar",
        description=(
            "El estado nunca cambia por `PATCH` (usa `/status-transitions`) ni el asesor "
            "(usa `/assignments`). Montos, plazo y modalidades van por `/financing`."
        ),
        parameters=[IF_MATCH],
        request=ApplicationUpdateSerializer,
        responses={
            200: ApplicationDetailSerializer,
            409: _error("STALE_VERSION o APPLICATION_NOT_EDITABLE"),
            428: _error("PRECONDITION_REQUIRED (falta If-Match)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        version = expected_version(request)
        serializer = ApplicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes: dict[str, Any] = {}
        if "purpose_code" in serializer.validated_data:
            changes["purpose_item"] = serializer.validated_data["purpose_code"]
        if "bank_product_id" in serializer.validated_data:
            changes["bank_product"] = services.resolve_bank_product(
                serializer.validated_data["bank_product_id"]
            )
        services.update_application(
            self.actor, application, expected_version=version, changes=changes
        )
        return _detail_response(self, application_id)


class ApplicationSummaryView(ApplicationView):
    required_permissions = {"GET": "applications.read_summary"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_summary",
        summary="Resumen operativo de la solicitud",
        description="Sin datos financieros ni del inmueble. Es lo que ve el broker.",
        responses={200: ApplicationSummarySerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        return Response(ApplicationSummarySerializer(application).data)


class ApplicationAssignmentView(ApplicationView):
    required_permissions = {"POST": "applications.assign"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_assignments_create",
        summary="Reasignar el asesor responsable",
        description=(
            "Conserva el historial. No cambia la versión del expediente. Si quien reasigna "
            "deja de tener acceso, responde `204`."
        ),
        request=AssignmentCreateSerializer,
        responses={
            200: ApplicationDetailSerializer,
            204: OpenApiResponse(description="Reasignada; el actor ya no tiene acceso."),
            409: _error("APPLICATION_CLOSED"),
            422: _error("ADVISOR_NOT_ELIGIBLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign_application(
            self.actor,
            application,
            advisor=serializer.validated_data["advisor_id"],
            reason=serializer.validated_data["reason"],
        )
        if not services.applications_visible_to(self.actor).filter(pk=application.pk).exists():
            return Response(status=status.HTTP_204_NO_CONTENT)
        return _detail_response(self, application_id)


class ClientApplicationsView(ApplicationView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="clients_applications_list",
        summary="Solicitudes visibles en las que participa el cliente",
        parameters=[STATUS_PARAM],
        responses={200: ApplicationSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, client_id: Any) -> Response:
        client = get_object_or_404(clients_visible_to(self.actor), pk=client_id)
        applications = services.client_applications(self.actor, client)
        application_status = _choice_param(request, "status", ApplicationStatus.values)
        if application_status:
            applications = applications.filter(status=application_status)
        page = self.paginate_queryset(applications.order_by("-created_at"))
        serializer_class = self.list_serializer_class()
        return self.get_paginated_response(serializer_class(page, many=True).data)


# --------------------------------------------------------------------------------------
# Participantes, perfil financiero e ingresos (API §17)
# --------------------------------------------------------------------------------------

PARTICIPANTS_TAG = "Application participants"
WRITE_ERRORS = {
    409: _error("STALE_VERSION, APPLICATION_NOT_EDITABLE o PARTICIPANT_INACTIVE"),
    428: _error("PRECONDITION_REQUIRED (falta If-Match)"),
    **NOT_FOUND,
    **COMMON_ERRORS,
}
CREATE_ERRORS = {
    409: _error("APPLICATION_NOT_EDITABLE o PARTICIPANT_INACTIVE"),
    **NOT_FOUND,
    **COMMON_ERRORS,
}
ETAG_NOTE = "Responde `ETag` con la versión de la solicitud."


def _application_etag(response: Response, application_id: Any) -> Response:
    """``ETag`` con la versión vigente de la solicitud, leída después del cambio."""
    version = CreditApplication.objects.values_list("version", flat=True).get(pk=application_id)
    return with_etag(response, version)


class ExpedienteView(ApplicationView):
    """Subrecursos con datos del expediente: el broker nunca los recibe (decisión 4).

    El alcance se resuelve desde la solicitud: un participante, perfil o fuente de una
    solicitud que el actor no ve responde 404.
    """

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if self.scope.is_restricted:
            raise PermissionDenied()

    def get_participant(self, participant_id: Any) -> ApplicationParticipant:
        return get_object_or_404(services.participants_visible_to(self.actor), pk=participant_id)

    def get_profile(self, profile_id: Any) -> FinancialProfile:
        return get_object_or_404(services.financial_profiles_visible_to(self.actor), pk=profile_id)

    def get_income_source(self, source_id: Any) -> IncomeSource:
        return get_object_or_404(services.income_sources_visible_to(self.actor), pk=source_id)

    def participant_response(self, participant_id: Any, **kwargs: Any) -> Response:
        participant = self.get_participant(participant_id)
        return _application_etag(
            Response(ApplicationParticipantSerializer(participant).data, **kwargs),
            participant.application_id,
        )

    def profile_response(self, participant: ApplicationParticipant, **kwargs: Any) -> Response:
        profile = get_object_or_404(
            services.financial_profiles_visible_to(self.actor), participant=participant
        )
        return _application_etag(
            Response(FinancialProfileSerializer(profile).data, **kwargs),
            participant.application_id,
        )


class ApplicationParticipantListView(ExpedienteView):
    required_permissions = {"GET": "applications.read", "POST": "applications.update"}

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="applications_participants_list",
        summary="Titular y participantes adicionales",
        description=f"Solo los vigentes, salvo `include_inactive=true`. {ETAG_NOTE}",
        parameters=[
            OpenApiParameter(
                "include_inactive",
                OpenApiTypes.BOOL,
                description="Incluye a los participantes retirados.",
            )
        ],
        responses={
            200: ApplicationParticipantSerializer(many=True),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        participants = services.participants_queryset().filter(application=application)
        if not parse_bool_param(request, "include_inactive"):
            participants = participants.filter(is_active=True)
        page = self.paginate_queryset(participants)
        response = self.get_paginated_response(
            ApplicationParticipantSerializer(page, many=True).data
        )
        return with_etag(response, application.version)

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="applications_participants_create",
        summary="Agregar un co-solicitante o deudor solidario",
        description=(
            "Recibe `client_id` de un cliente visible o los datos de identidad, con los que "
            "crea el cliente (`409 DUPLICATE_CLIENT_DOCUMENT` si el documento ya existe). "
            "Un participante retirado se reactiva. No exige `If-Match`, pero aumenta la "
            f"versión. {ETAG_NOTE}"
        ),
        request=ParticipantCreateSerializer,
        responses={
            201: ApplicationParticipantSerializer,
            409: _error("APPLICATION_NOT_EDITABLE o DUPLICATE_CLIENT_DOCUMENT"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = ParticipantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = (
            resolve_visible_client(self.actor, data["client_id"])
            if data["client_data"] is None
            else None
        )
        participant = services.add_participant(
            self.actor,
            application,
            role=data["role_code"],
            client=client,
            client_data=data["client_data"],
            contributes_income=data["contributes_income"],
            income_share_cop=data["income_share_cop"],
        )
        return self.participant_response(participant.pk, status=status.HTTP_201_CREATED)


class ApplicationParticipantDetailView(ExpedienteView):
    required_permissions = {
        "GET": "applications.read",
        "PATCH": "applications.update",
        "DELETE": "applications.update",
    }

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="application_participants_retrieve",
        summary="Detalle del participante",
        description=f"También de un participante retirado (`is_active=false`). {ETAG_NOTE}",
        responses={200: ApplicationParticipantSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, participant_id: Any) -> Response:
        return self.participant_response(participant_id)

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="application_participants_partial_update",
        summary="Cambiar el papel o el aporte de ingresos",
        description=(
            "El titular no cambia de papel. Los datos personales se corrigen en "
            f"`/clients/{{id}}`. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH],
        request=ParticipantUpdateSerializer,
        responses={200: ApplicationParticipantSerializer, **WRITE_ERRORS},
    )
    def patch(self, request: Request, participant_id: Any) -> Response:
        participant = self.get_participant(participant_id)
        version = expected_version(request)
        serializer = ParticipantUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_participant(
            self.actor, participant, expected_version=version, changes=serializer.changes()
        )
        return self.participant_response(participant_id)

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="application_participants_destroy",
        summary="Retirar un participante adicional",
        description=(
            "Lo marca `is_active=false`; el titular no se retira. No exige `If-Match`, pero "
            f"aumenta la versión. {ETAG_NOTE}"
        ),
        responses={
            204: OpenApiResponse(description="Retirado."),
            409: _error("APPLICATION_NOT_EDITABLE"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def delete(self, request: Request, participant_id: Any) -> Response:
        participant = self.get_participant(participant_id)
        services.remove_participant(self.actor, participant)
        return _application_etag(
            Response(status=status.HTTP_204_NO_CONTENT), participant.application_id
        )


class FinancialProfileView(ExpedienteView):
    required_permissions = {"GET": "applications.read", "PUT": "applications.update"}

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="application_participants_financial_profile_retrieve",
        summary="Perfil financiero del participante",
        description=(
            "`income_sources_total_cop` suma las fuentes de ingreso; es informativo y puede "
            f"diferir de `monthly_income_cop`. {ETAG_NOTE}"
        ),
        responses={200: FinancialProfileSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, participant_id: Any) -> Response:
        return self.profile_response(self.get_participant(participant_id))

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="application_participants_financial_profile_update",
        summary="Crear o reemplazar el perfil financiero",
        description=(
            "Reemplazo completo: lo que no llega vuelve a su valor por omisión. "
            "`data_confirmed_at` lo fija el comprador (paso 9). Responde `201` si lo creó. "
            f"{ETAG_NOTE}"
        ),
        parameters=[IF_MATCH],
        request=FinancialProfileInputSerializer,
        responses={
            200: FinancialProfileSerializer,
            201: FinancialProfileSerializer,
            **WRITE_ERRORS,
        },
    )
    def put(self, request: Request, participant_id: Any) -> Response:
        participant = self.get_participant(participant_id)
        version = expected_version(request)
        serializer = FinancialProfileInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.put_financial_profile(
            self.actor, participant, expected_version=version, values=serializer.model_values()
        )
        return self.profile_response(
            participant, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class IncomeSourceListView(ExpedienteView):
    required_permissions = {"GET": "applications.read", "POST": "applications.update"}

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="financial_profiles_income_sources_list",
        summary="Fuentes de ingreso del perfil",
        description=f"La principal primero. {ETAG_NOTE}",
        responses={200: IncomeSourceSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, profile_id: Any) -> Response:
        profile = self.get_profile(profile_id)
        sources = profile.income_sources.select_related("source_type_item")
        page = self.paginate_queryset(sources)
        response = self.get_paginated_response(IncomeSourceSerializer(page, many=True).data)
        return _application_etag(response, profile.participant.application_id)

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="financial_profiles_income_sources_create",
        summary="Agregar una fuente de ingreso",
        description=(
            "Si llega con `is_primary`, la principal anterior deja de serlo. No exige "
            f"`If-Match`, pero aumenta la versión. {ETAG_NOTE}"
        ),
        request=IncomeSourceCreateSerializer,
        responses={201: IncomeSourceSerializer, **CREATE_ERRORS},
    )
    def post(self, request: Request, profile_id: Any) -> Response:
        profile = self.get_profile(profile_id)
        serializer = IncomeSourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = services.add_income_source(self.actor, profile, serializer.model_values())
        return _application_etag(
            Response(
                IncomeSourceSerializer(self.get_income_source(source.pk)).data,
                status=status.HTTP_201_CREATED,
            ),
            profile.participant.application_id,
        )


class IncomeSourceDetailView(ExpedienteView):
    required_permissions = {"PATCH": "applications.update", "DELETE": "applications.update"}

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="income_sources_partial_update",
        summary="Editar una fuente de ingreso",
        description=f"Marcarla como principal desmarca la anterior. {ETAG_NOTE}",
        parameters=[IF_MATCH],
        request=IncomeSourceUpdateSerializer,
        responses={200: IncomeSourceSerializer, **WRITE_ERRORS},
    )
    def patch(self, request: Request, income_source_id: Any) -> Response:
        source = self.get_income_source(income_source_id)
        version = expected_version(request)
        serializer = IncomeSourceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_income_source(
            self.actor, source, expected_version=version, changes=serializer.model_values()
        )
        return _application_etag(
            Response(IncomeSourceSerializer(self.get_income_source(income_source_id)).data),
            source.financial_profile.participant.application_id,
        )

    @extend_schema(
        tags=[PARTICIPANTS_TAG],
        operation_id="income_sources_destroy",
        summary="Eliminar una fuente de ingreso",
        description=f"No exige `If-Match`, pero aumenta la versión. {ETAG_NOTE}",
        responses={
            204: OpenApiResponse(description="Eliminada."),
            **CREATE_ERRORS,
        },
    )
    def delete(self, request: Request, income_source_id: Any) -> Response:
        source = self.get_income_source(income_source_id)
        services.delete_income_source(self.actor, source)
        return _application_etag(
            Response(status=status.HTTP_204_NO_CONTENT),
            source.financial_profile.participant.application_id,
        )
