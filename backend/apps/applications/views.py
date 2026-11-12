"""Endpoints de solicitudes de crédito (API §16), sus participantes, perfiles financieros
e ingresos (§17), inmueble, financiación y reglas bancarias (§18), estados, desistimiento,
historial, acciones disponibles y completitud (§16 y §9) y
`GET /clients/{id}/applications` (§13)."""

from typing import Any, cast

from django.db.models import CharField, Count, F, Q, QuerySet, Value
from django.db.models.functions import Concat
from django.http import Http404
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
    FinancingPreference,
    IncomeSource,
    Property,
)
from apps.applications.quick_filters import (
    ALL,
    QUICK_FILTER_CODES,
    QUICK_FILTERS,
    QUICK_FILTERS_BY_CODE,
)
from apps.applications.serializers import (
    DETAIL_INCLUDES,
    ApplicationCreateSerializer,
    ApplicationDetailSerializer,
    ApplicationParticipantSerializer,
    ApplicationPropertyInputSerializer,
    ApplicationSerializer,
    ApplicationSummarySerializer,
    ApplicationUpdateSerializer,
    AssignmentCreateSerializer,
    AvailableActionSerializer,
    BankRuleEvaluationSerializer,
    CompletenessSerializer,
    EligibleBankProductSerializer,
    FinancialProfileInputSerializer,
    FinancialProfileSerializer,
    FinancingInputSerializer,
    FinancingSerializer,
    IncomeSourceCreateSerializer,
    IncomeSourceSerializer,
    IncomeSourceUpdateSerializer,
    ParticipantCreateSerializer,
    ParticipantUpdateSerializer,
    PropertySerializer,
    QuickFilterSerializer,
    StatusChangeSerializer,
    StatusHistorySerializer,
    StatusTransitionSerializer,
    WithdrawalSerializer,
    property_model_values,
)
from apps.catalogs.models import CatalogItem
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
QUICK_FILTER_PARAM = OpenApiParameter(
    "quick_filter",
    OpenApiTypes.STR,
    enum=QUICK_FILTER_CODES,
    description="Pestaña rápida (`/applications/quick-filters`). `all` no filtra; junto con "
    "`status` se aplican los dos. Un código desconocido responde `400`.",
)
INCLUDE_PARAM = OpenApiParameter(
    "include",
    OpenApiTypes.STR,
    description=(
        "Bloques opcionales separados por comas: `participants` (vigentes) y `financing`. "
        "`property` se admite, pero sale siempre. El broker recibe el resumen y este "
        "parámetro se ignora."
    ),
)


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


def _catalog_param(request: Request, name: str, catalog_code: str) -> str | None:
    """Código de un catálogo en ``?name=``. Uno que no existe en el catálogo (activo o
    inactivo, para poder filtrar el histórico) responde 400."""
    value = request.query_params.get(name)
    if not value:
        return None
    codes = list(
        CatalogItem.objects.filter(catalog__code=catalog_code)
        .order_by("code")
        .values_list("code", flat=True)
    )
    if value not in codes:
        raise ValidationError({name: [f"Valor no permitido. Opciones: {', '.join(codes)}."]})
    return value


# Filtros por código de catálogo del listado: parámetro, catálogo y campo.
CATALOG_FILTERS = (
    ("purpose", "loan_purpose", "purpose_item__code"),
    ("origin", "lead_origin", "opportunity__origin_item__code"),
    ("product_type", "bank_product_type", "bank_product__product_type_item__code"),
)
# Filtros por id del listado: parámetro y campo.
UUID_FILTERS = (
    ("bank_id", "bank_product__bank_id"),
    ("product_id", "bank_product_id"),
    ("advisor_id", "assigned_advisor_id"),
    ("project_id", "financed_property__project_id"),
)
APPLICATION_SEARCH_FIELDS = [
    "code",
    "opportunity__client__first_names",
    "opportunity__client__last_names",
    "opportunity__client__document_number",
]


def _filtered_applications(view: "ApplicationView") -> QuerySet[CreditApplication]:
    """Solicitudes visibles para el actor con los filtros del listado que no son de
    estado (los comparten el listado y las pestañas). La búsqueda la agrega
    ``SearchFilter``."""
    applications = services.applications_visible_to(view.actor)
    for param, field in UUID_FILTERS:
        value = parse_uuid_param(view.request, param)
        if value:
            applications = applications.filter(**{field: value})
    for param, catalog_code, field in CATALOG_FILTERS:
        code = _catalog_param(view.request, param, catalog_code)
        if code:
            applications = applications.filter(**{field: code})
    return applications


LIST_FILTER_PARAMETERS = [
    OpenApiParameter("bank_id", OpenApiTypes.UUID),
    OpenApiParameter("product_id", OpenApiTypes.UUID),
    OpenApiParameter(
        "purpose",
        OpenApiTypes.STR,
        description="Código `loan_purpose`. Uno que no existe responde `400`.",
    ),
    OpenApiParameter(
        "product_type",
        OpenApiTypes.STR,
        description="Tipo de crédito: código `bank_product_type`. Uno que no existe "
        "responde `400`.",
    ),
    OpenApiParameter("advisor_id", OpenApiTypes.UUID),
    OpenApiParameter("project_id", OpenApiTypes.UUID),
    OpenApiParameter(
        "origin",
        OpenApiTypes.STR,
        description="Código `lead_origin`. Uno que no existe responde `400`.",
    ),
]


def _include_param(request: Request) -> frozenset[str]:
    """Bloques de ``?include=`` (separados por comas). Uno desconocido responde 400."""
    raw = request.query_params.get("include", "")
    blocks = frozenset(part.strip() for part in raw.split(",") if part.strip())
    unknown = sorted(blocks - set(DETAIL_INCLUDES))
    if unknown:
        raise ValidationError(
            {
                "include": [
                    f"Valores no permitidos: {', '.join(unknown)}. "
                    f"Opciones: {', '.join(DETAIL_INCLUDES)}."
                ]
            }
        )
    return blocks


def _detail_response(
    view: ApplicationView,
    application_id: Any,
    include: frozenset[str] = frozenset(),
    **kwargs: Any,
) -> Response:
    """Detalle según el actor: el broker solo recibe el resumen (sin ``include``)."""
    if view.scope.is_restricted:
        summary = view.get_application(application_id)
        return with_etag(
            Response(ApplicationSummarySerializer(summary).data, **kwargs), summary.version
        )
    application = services.application_detail(view.actor, application_id, include)
    if application is None:
        raise Http404
    context = {
        "include": include,
        "available_actions": services.available_actions(view.actor, application),
    }
    data = ApplicationDetailSerializer(application, context=context).data
    return with_etag(Response(data, **kwargs), application.version)


class ApplicationListView(ApplicationView):
    required_permissions = {"GET": "applications.read", "POST": "applications.create"}
    filter_backends = [SearchFilter, StrictOrderingFilter]
    search_fields = APPLICATION_SEARCH_FIELDS
    ordering_fields = [
        "created_at",
        "updated_at",
        "status",
        "code",
        "requested_amount",
        "bank_name",
        "applicant_name",
    ]
    ordering = ["-created_at"]
    # Sin financiación o sin banco elegido, la fila va al final en los dos sentidos.
    ordering_nulls_last = True

    def get_queryset(self) -> QuerySet[CreditApplication]:
        applications = _filtered_applications(self)
        application_status = _choice_param(self.request, "status", ApplicationStatus.values)
        if application_status:
            applications = applications.filter(status=application_status)
        # Pestaña rápida: junto con `status` se aplican los dos.
        quick_code = _choice_param(self.request, "quick_filter", QUICK_FILTER_CODES)
        if quick_code and quick_code != ALL:
            applications = applications.filter(
                status__in=QUICK_FILTERS_BY_CODE[quick_code].statuses
            )
        # Campos de orden con nombre propio.
        return applications.annotate(
            requested_amount=F("financing__requested_amount_cop"),
            bank_name=F("bank_product__bank__name"),
            applicant_name=Concat(
                "opportunity__client__first_names",
                Value(" "),
                "opportunity__client__last_names",
                output_field=CharField(),
            ),
        )

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
            QUICK_FILTER_PARAM,
            *LIST_FILTER_PARAMETERS,
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
        context = {"available_actions": services.available_actions(self.actor, created)}
        return with_etag(
            Response(
                ApplicationDetailSerializer(created, context=context).data,
                status=status.HTTP_201_CREATED,
            ),
            created.version,
        )


class ApplicationQuickFiltersView(ApplicationView):
    """Pestañas rápidas con sus conteos (precisión B). El broker también las ve: solo
    conteos, dentro de su alcance."""

    required_permissions = {"GET": "applications.read"}
    filter_backends = [SearchFilter]
    search_fields = APPLICATION_SEARCH_FIELDS
    # Lista corta y fija: un arreglo sin paginar, como `/available-actions`.
    pagination_class = None

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_quick_filters",
        summary="Pestañas rápidas del listado con sus conteos",
        description=(
            "Cada pestaña con los estados que agrupa y cuántas solicitudes tiene, en el "
            "orden del listado. Cuenta solo lo que el actor puede ver (asesor: lo asignado; "
            "broker: lo que originó; administrador: todo) y aplica los mismos filtros y la "
            "misma búsqueda del listado, para que el número coincida con lo que se ve al "
            "elegir la pestaña. Ignora `status`, `quick_filter`, la paginación y el orden. "
            "Los conteos salen de una sola consulta. Cada estado está en exactamente una "
            "pestaña, así que la suma de las demás es igual a `all`."
        ),
        parameters=LIST_FILTER_PARAMETERS,
        responses={200: QuickFilterSerializer(many=True), **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        applications = self.filter_queryset(_filtered_applications(self))
        # Una sola consulta: un conteo por pestaña sobre las mismas solicitudes.
        counts = CreditApplication.objects.filter(pk__in=applications.values("pk")).aggregate(
            **{
                quick.code: Count("pk", filter=Q(status__in=quick.statuses))
                if quick.statuses
                else Count("pk")
                for quick in QUICK_FILTERS
            }
        )
        data = [
            {
                "code": quick.code,
                "label": quick.label,
                "statuses": list(quick.statuses),
                "count": counts[quick.code],
            }
            for quick in QUICK_FILTERS
        ]
        return Response(QuickFilterSerializer(data, many=True).data)


class ApplicationDetailView(ApplicationView):
    required_permissions = {"GET": "applications.read", "PATCH": "applications.update"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_retrieve",
        summary="Expediente según el rol",
        description=(
            "Responde `ETag` con la versión, que se reenvía en `If-Match` al editar. "
            "`property` y `assignments` salen siempre; `participants` y `financing`, solo "
            "con `include`. El broker recibe solo el resumen."
        ),
        parameters=[INCLUDE_PARAM],
        responses={200: ApplicationDetailSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        include = frozenset() if self.scope.is_restricted else _include_param(request)
        return _detail_response(self, application_id, include)

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_partial_update",
        summary="Cambiar la finalidad o el producto antes de radicar",
        description=(
            "El estado nunca cambia por `PATCH` (usa `/status-transitions`) ni el asesor "
            "(usa `/assignments`). Montos, plazo y modalidades van por `/financing`. Con "
            "una financiación registrada, el producto debe cuadrar con su modalidad: solo "
            "`BANK_CREDIT` lleva producto, y no se puede dejar sin él."
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
            "`data_confirmed_at` lo fija el comprador al confirmar, y un cambio real lo "
            "limpia. Responde `201` si lo creó. "
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


# --------------------------------------------------------------------------------------
# Inmueble y financiación (API §18.1 y §18.2)
# --------------------------------------------------------------------------------------

PROPERTY_TAG = "Application property and financing"
PUT_ERRORS = {
    409: _error("STALE_VERSION o APPLICATION_NOT_EDITABLE"),
    428: _error("PRECONDITION_REQUIRED (falta If-Match)"),
    **NOT_FOUND,
    **COMMON_ERRORS,
}


class ApplicationPropertyView(ExpedienteView):
    required_permissions = {"GET": "applications.read", "PUT": "applications.update"}

    def property_response(self, application_id: Any, **kwargs: Any) -> Response:
        prop = get_object_or_404(
            Property.objects.select_related(
                "project", "property_type_item", "condition_item", "city_item"
            ),
            application_id=application_id,
        )
        return _application_etag(Response(PropertySerializer(prop).data, **kwargs), application_id)

    @extend_schema(
        tags=[PROPERTY_TAG],
        operation_id="applications_property_retrieve",
        summary="Inmueble de la solicitud",
        description=f"`404` si todavía no se registró. {ETAG_NOTE}",
        responses={200: PropertySerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        return self.property_response(application.pk)

    @extend_schema(
        tags=[PROPERTY_TAG],
        operation_id="applications_property_update",
        summary="Crear o reemplazar el inmueble",
        description=(
            "Reemplazo completo: lo que no llega vuelve a su valor por omisión. Reglas por "
            "finalidad: solo `PURCHASE_NEW` admite `project_id` (proyecto `ACTIVE`); "
            "`PURCHASE_USED` y `HOME_IMPROVEMENT` exigen `address`; `HOME_IMPROVEMENT` "
            f"exige `is_owned_by_applicant`. Responde `201` si lo creó. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH],
        request=ApplicationPropertyInputSerializer,
        responses={
            200: PropertySerializer,
            201: PropertySerializer,
            422: _error("PROJECT_NOT_ACTIVE"),
            **PUT_ERRORS,
        },
    )
    def put(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        version = expected_version(request)
        serializer = ApplicationPropertyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = property_model_values(serializer.validated_data)
        values["project"] = services.resolve_property_project(
            self.actor, serializer.validated_data["project_id"]
        )
        created = services.put_property(
            self.actor, application, expected_version=version, values=values
        )
        return self.property_response(
            application.pk, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class ApplicationFinancingView(ExpedienteView):
    required_permissions = {"GET": "applications.read", "PUT": "applications.update"}

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
        return _application_etag(
            Response(FinancingSerializer(financing).data, **kwargs), application_id
        )

    @extend_schema(
        tags=[PROPERTY_TAG],
        operation_id="applications_financing_retrieve",
        summary="Preferencia de financiación",
        description=f"`404` si todavía no se registró. {ETAG_NOTE}",
        responses={200: FinancingSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        return self.financing_response(application.pk)

    @extend_schema(
        tags=[PROPERTY_TAG],
        operation_id="applications_financing_update",
        summary="Crear o reemplazar la financiación y el producto elegido",
        description=(
            "Reemplazo completo. `BANK_CREDIT` exige `bank_product_id` (disponible para "
            "la finalidad) y `requested_amount_cop`. Con `OWN_FUNDS` o `EXTERNAL_CREDIT` "
            "no se envía producto (se limpia el de la solicitud) y el monto solicitado "
            "queda en 0. `external_approved_amount_cop` es obligatorio con "
            "`EXTERNAL_CREDIT` y no se acepta en los otros modos. Sin "
            "`uses_severance_funds`, `severance_funds_cop` es 0. Los rangos del producto "
            "no se validan al guardar: los verifica la evaluación bancaria. Responde "
            f"`201` si la creó. {ETAG_NOTE}"
        ),
        parameters=[IF_MATCH],
        request=FinancingInputSerializer,
        responses={
            200: FinancingSerializer,
            201: FinancingSerializer,
            **PUT_ERRORS,
        },
    )
    def put(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        version = expected_version(request)
        serializer = FinancingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = services.resolve_bank_product(serializer.validated_data["bank_product_id"])
        created = services.put_financing(
            self.actor,
            application,
            expected_version=version,
            values=serializer.model_values(),
            product=product,
        )
        return self.financing_response(
            application.pk, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# --------------------------------------------------------------------------------------
# Reglas bancarias (API §18.2)
# --------------------------------------------------------------------------------------

BANK_RULES_TAG = "Application bank rules"


class ApplicationRuleEvaluationView(ExpedienteView):
    required_permissions = {"POST": "applications.update"}

    @extend_schema(
        tags=[BANK_RULES_TAG],
        operation_id="applications_bank_rule_evaluations_create",
        summary="Evaluar las reglas del producto elegido",
        description=(
            "Aplica las reglas publicadas del producto para la finalidad y los rangos de "
            "monto y plazo del producto (`PRODUCT_AMOUNT_RANGE` y `PRODUCT_TERM_RANGE`, "
            "siempre bloqueantes), y guarda el resultado con la versión actual. Una regla "
            "bloqueante incumplida o sin datos (`MISSING_DATA`) deja `eligible = false`. "
            "No aprueba ni rechaza el crédito, no cambia el estado ni la versión y no "
            f"exige `If-Match`. Solo antes de radicar. {ETAG_NOTE}"
        ),
        request=None,
        responses={
            201: BankRuleEvaluationSerializer,
            409: _error("APPLICATION_NOT_EDITABLE"),
            422: _error("BANK_PRODUCT_REQUIRED (la solicitud no tiene producto)"),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        evaluation = services.evaluate_application(self.actor, application)
        data = BankRuleEvaluationSerializer(
            evaluation, context={"application": evaluation.application}
        ).data
        return with_etag(
            Response(data, status=status.HTTP_201_CREATED), evaluation.application_version
        )


class ApplicationLatestRuleEvaluationView(ExpedienteView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[BANK_RULES_TAG],
        operation_id="applications_bank_rule_evaluations_latest",
        summary="Última evaluación de reglas",
        description=(
            "La más reciente, aunque la solicitud haya cambiado después: `is_current` dice "
            "si corresponde a la versión y al producto actuales. `404` si nunca se evaluó. "
            f"{ETAG_NOTE}"
        ),
        responses={200: BankRuleEvaluationSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        evaluation = services.latest_evaluation(application)
        if evaluation is None:
            raise Http404
        data = BankRuleEvaluationSerializer(evaluation, context={"application": application}).data
        return with_etag(Response(data), application.version)


class EligibleBankProductsView(ExpedienteView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[BANK_RULES_TAG],
        operation_id="applications_eligible_bank_products",
        summary="Productos disponibles para la finalidad, con su evaluación",
        description=(
            "Productos activos y vigentes (con banco activo) que admiten la finalidad, por "
            "banco y producto. Cada uno trae una evaluación **no guardada** con los datos "
            "actuales: reglas publicadas y rangos del producto. Se listan aunque la "
            f"modalidad registrada no sea `BANK_CREDIT`. {ETAG_NOTE}"
        ),
        responses={
            200: EligibleBankProductSerializer(many=True),
            **NOT_FOUND,
            **COMMON_ERRORS,
        },
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        page = self.paginate_queryset(services.eligible_products_queryset(application)) or []
        evaluations = services.preview_products(application, page)
        response = self.get_paginated_response(
            EligibleBankProductSerializer(
                page, many=True, context={"evaluations": evaluations}
            ).data
        )
        return with_etag(response, application.version)


# --------------------------------------------------------------------------------------
# Estados, desistimiento, historial, acciones y completitud (API §16 y §9)
# --------------------------------------------------------------------------------------

STATUS_ERRORS = {
    409: _error("STALE_VERSION, APPLICATION_CLOSED o INVALID_STATE_TRANSITION"),
    **NOT_FOUND,
    **COMMON_ERRORS,
}


def _status_change_response(change: services.StatusChange) -> Response:
    return with_etag(Response(StatusChangeSerializer(change).data), change.application.version)


class ApplicationStatusTransitionView(ExpedienteView):
    required_permissions = {"POST": "applications.transition"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_status_transitions_create",
        summary="Cambiar el estado de la solicitud",
        description=(
            "Ejecuta una transición configurada del flujo `APPLICATION`. `expected_version` "
            "es obligatorio (no se usa `If-Match`). `WITHDRAWN` va por `/withdrawals`. "
            "`CANCELLED`, `OWN_FUNDS` y `EXTERNAL_CREDIT_APPROVED` exigen `reason_code`; los "
            "dos últimos, además, la modalidad de financiación correspondiente. "
            "`READY_TO_FILE` evalúa la guarda `APPLICATION_READY_TO_FILE`: si la última "
            "evaluación bancaria no está vigente, evalúa y la guarda aunque la transición "
            f"se rechace. {ETAG_NOTE}"
        ),
        request=StatusTransitionSerializer,
        responses={
            200: StatusChangeSerializer,
            422: _error("APPLICATION_NOT_READY o FINANCING_MODE_MISMATCH"),
            **STATUS_ERRORS,
        },
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = StatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change = services.transition_application(
            self.actor,
            application,
            to_status=data["target_status"],
            expected_version=data["expected_version"],
            reason=data["reason_code"],
            comment=data["comment"],
        )
        return _status_change_response(change)


class ApplicationWithdrawalView(ExpedienteView):
    required_permissions = {"POST": "applications.withdraw"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_withdrawals_create",
        summary="Registrar el desistimiento",
        description=(
            "Pasa la solicitud a `WITHDRAWN` desde cualquier estado no terminal, también "
            "después de radicar. `reason_code` (catálogo `application_withdrawal_reason`) y "
            f"`expected_version` son obligatorios. {ETAG_NOTE}"
        ),
        request=WithdrawalSerializer,
        responses={200: StatusChangeSerializer, **STATUS_ERRORS},
    )
    def post(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        serializer = WithdrawalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change = services.withdraw_application(
            self.actor,
            application,
            expected_version=data["expected_version"],
            reason=data["reason_code"],
            comment=data["comment"],
        )
        return _status_change_response(change)


class ApplicationStatusHistoryView(ExpedienteView):
    required_permissions = {"GET": "applications.read_history"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_status_history",
        summary="Historial de estados",
        description=(
            "De la más reciente a la más antigua, incluido el registro de creación "
            f"(`from_status` nulo). {ETAG_NOTE}"
        ),
        responses={200: StatusHistorySerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        page = self.paginate_queryset(services.status_history_queryset(application))
        response = self.get_paginated_response(StatusHistorySerializer(page, many=True).data)
        return with_etag(response, application.version)


class ApplicationAvailableActionsView(ExpedienteView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_available_actions",
        summary="Acciones disponibles",
        description=(
            "Transiciones que el actor puede ejecutar desde el estado actual según su rol "
            "y permiso. La guarda no se evalúa aquí. `WITHDRAW_*` se ejecuta por "
            f"`/withdrawals`. {ETAG_NOTE}"
        ),
        responses={200: AvailableActionSerializer(many=True), **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        actions = services.available_actions(self.actor, application)
        return with_etag(
            Response(AvailableActionSerializer(actions, many=True).data), application.version
        )


class ApplicationCompletenessView(ExpedienteView):
    required_permissions = {"GET": "applications.read"}

    @extend_schema(
        tags=[APPLICATIONS_TAG],
        operation_id="applications_completeness",
        summary="Completitud del expediente",
        description=(
            "Ítems de datos (inmueble, financiación, producto y evaluación bancaria cuando "
            "aplica, y el perfil de cada participante que aporta ingresos) y documentos "
            "obligatorios. `percentage` es el promedio, entero hacia abajo, de "
            "`data_percentage` y `documents_percentage`; un grupo alternativo cuenta como "
            "un documento y se cumple con un juego completo de un mismo tipo. "
            "`ready_to_file` es la guarda de `READY_TO_FILE` sin problemas, y "
            "`ready_to_file_problems` trae los mismos `details` que daría su `422`. Una "
            "solicitud en `READY_TO_FILE` que deja de cumplir sigue en ese estado y aquí "
            "aparece con `ready_to_file = false`. Es solo lectura: si la última evaluación "
            f"bancaria no está vigente, evalúa en memoria sin guardarla. {ETAG_NOTE}"
        ),
        responses={200: CompletenessSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, application_id: Any) -> Response:
        application = self.get_application(application_id)
        data = CompletenessSerializer(services.completeness(application)).data
        return with_etag(Response(data), application.version)
