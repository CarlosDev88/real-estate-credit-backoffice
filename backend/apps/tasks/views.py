"""Tareas manuales (API §15.2). Las reglas viven en ``apps.tasks.services``."""

from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.applications.views import _catalog_param, _choice_param
from apps.identity.models import User
from apps.identity.permissions import HasPermissionCode
from apps.tasks import services
from apps.tasks.models import PRIORITY_CATALOG, Task, TaskStatus
from apps.tasks.serializers import (
    TaskCancelSerializer,
    TaskCreateSerializer,
    TaskSerializer,
    TaskUpdateSerializer,
)
from config.filters import parse_uuid_param
from config.serializers import ErrorSerializer

TASKS_TAG = "Tasks"


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


COMMON_ERRORS = {
    401: _error("NOT_AUTHENTICATED o SESSION_EXPIRED"),
    403: _error("PERMISSION_DENIED o CSRF_FAILED"),
}
NOT_FOUND = {404: _error("RESOURCE_NOT_FOUND (inexistente o fuera del alcance)")}
NOT_PENDING = {409: _error("TASK_NOT_PENDING (completada o cancelada)")}
VALIDATION = {400: _error("VALIDATION_ERROR")}

LIST_PARAMETERS = [
    OpenApiParameter("status", OpenApiTypes.STR, enum=TaskStatus.values),
    OpenApiParameter("application_id", OpenApiTypes.UUID),
    OpenApiParameter("opportunity_id", OpenApiTypes.UUID),
    OpenApiParameter(
        "assigned_to_id",
        OpenApiTypes.UUID,
        description="Solo el administrador. Para el asesor se ignora.",
    ),
    OpenApiParameter(
        "due",
        OpenApiTypes.STR,
        enum=list(services.DueWindow.values),
        description=(
            "Tareas `PENDING` con `due_at` antes de hoy (`overdue`), hoy (`today`) o "
            "después de hoy (`upcoming`), con la fecha de Bogotá. Las que no tienen fecha "
            "no entran en ninguno."
        ),
    ),
    OpenApiParameter(
        "priority",
        OpenApiTypes.STR,
        description="Código `task_priority`. Uno que no existe responde `400`.",
    ),
]


class TaskView(GenericAPIView):
    permission_classes = [HasPermissionCode]
    required_permissions: dict[str, str] = {}

    @property
    def actor(self) -> User:
        return cast(User, self.request.user)

    def get_task(self, task_id: Any) -> Task:
        return get_object_or_404(services.tasks_visible_to(self.actor), pk=task_id)

    def task_response(self, task: Task, status_code: int = status.HTTP_200_OK) -> Response:
        fresh = services.tasks_queryset().get(pk=task.pk)
        return Response(TaskSerializer(fresh).data, status=status_code)


class TaskListView(TaskView):
    required_permissions = {"GET": "tasks.read", "POST": "tasks.create"}

    def get_queryset(self) -> Any:
        tasks = services.tasks_visible_to(self.actor)
        task_status = _choice_param(self.request, "status", TaskStatus.values)
        if task_status:
            tasks = tasks.filter(status=task_status)
        application_id = parse_uuid_param(self.request, "application_id")
        if application_id:
            tasks = tasks.filter(application_id=application_id)
        opportunity_id = parse_uuid_param(self.request, "opportunity_id")
        if opportunity_id:
            tasks = tasks.filter(opportunity_id=opportunity_id)
        if services.sees_everything(self.actor):
            assigned_to_id = parse_uuid_param(self.request, "assigned_to_id")
            if assigned_to_id:
                tasks = tasks.filter(assigned_to_id=assigned_to_id)
        due = _choice_param(self.request, "due", list(services.DueWindow.values))
        if due:
            tasks = tasks.filter(services.due_condition(due))
        priority = _catalog_param(self.request, "priority", PRIORITY_CATALOG)
        if priority:
            tasks = tasks.filter(priority_item__code=priority)
        return tasks.order_by(*services.LIST_ORDERING)

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_list",
        summary="Tareas dentro del alcance",
        description=(
            "El administrador ve todas; el asesor, las asignadas a él y las de sus "
            "solicitudes u oportunidades. Ordenadas por `due_at` (las que no tienen fecha "
            "al final) y después por creación."
        ),
        parameters=LIST_PARAMETERS,
        responses={200: TaskSerializer(many=True), **VALIDATION, **COMMON_ERRORS},
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(TaskSerializer(page, many=True).data)

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_create",
        summary="Crear una tarea manual",
        description=(
            "Exactamente uno de `application_id` u `opportunity_id`, dentro del alcance del "
            "actor (si no, `400`). El responsable (por omisión, el actor) debe ser un "
            "usuario activo administrador o asesor. Una solicitud terminada responde "
            "`409 APPLICATION_CLOSED`."
        ),
        request=TaskCreateSerializer,
        responses={
            201: TaskSerializer,
            **VALIDATION,
            409: _error("APPLICATION_CLOSED"),
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        parent = services.resolve_parent(
            self.actor,
            application_id=data["application_id"],
            opportunity_id=data["opportunity_id"],
        )
        assignee = (
            services.resolve_assignee(data["assigned_to_id"]) if data["assigned_to_id"] else None
        )
        task = services.create_task(
            self.actor,
            parent=parent,
            title=data["title"],
            description=data.get("description", ""),
            assignee=assignee,
            due_at=data["due_at"],
            priority=data.get("priority_code"),
        )
        return self.task_response(task, status.HTTP_201_CREATED)


class TaskDetailView(TaskView):
    required_permissions = {"GET": "tasks.read", "PATCH": "tasks.update"}

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_retrieve",
        summary="Detalle de una tarea",
        responses={200: TaskSerializer, **NOT_FOUND, **COMMON_ERRORS},
    )
    def get(self, request: Request, task_id: Any) -> Response:
        return Response(TaskSerializer(self.get_task(task_id)).data)

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_partial_update",
        summary="Editar una tarea pendiente",
        description=(
            "Título, descripción, responsable, `due_at` (nulo la deja sin fecha) y "
            "prioridad. Solo una tarea `PENDING`; si no, `409 TASK_NOT_PENDING`."
        ),
        request=TaskUpdateSerializer,
        responses={
            200: TaskSerializer,
            **VALIDATION,
            **NOT_FOUND,
            **NOT_PENDING,
            **COMMON_ERRORS,
        },
    )
    def patch(self, request: Request, task_id: Any) -> Response:
        task = self.get_task(task_id)
        serializer = TaskUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        changes: dict[str, Any] = {
            field: data[field] for field in ("title", "description", "due_at") if field in data
        }
        if "priority_code" in data:
            changes["priority_item"] = data["priority_code"]
        if "assigned_to_id" in data:
            changes["assigned_to"] = services.resolve_assignee(data["assigned_to_id"])
        return self.task_response(services.update_task(self.actor, task, changes))


class TaskCompleteView(TaskView):
    required_permissions = {"POST": "tasks.complete"}

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_complete",
        summary="Completar una tarea",
        description="Solo desde `PENDING`; si no, `409 TASK_NOT_PENDING`.",
        request=None,
        responses={200: TaskSerializer, **NOT_FOUND, **NOT_PENDING, **COMMON_ERRORS},
    )
    def post(self, request: Request, task_id: Any) -> Response:
        task = self.get_task(task_id)
        return self.task_response(services.complete_task(self.actor, task))


class TaskCancelView(TaskView):
    required_permissions = {"POST": "tasks.cancel"}

    @extend_schema(
        tags=[TASKS_TAG],
        operation_id="tasks_cancel",
        summary="Cancelar una tarea con motivo",
        description="`reason` es obligatorio. Solo desde `PENDING`; si no, `409 TASK_NOT_PENDING`.",
        request=TaskCancelSerializer,
        responses={
            200: TaskSerializer,
            **VALIDATION,
            **NOT_FOUND,
            **NOT_PENDING,
            **COMMON_ERRORS,
        },
    )
    def post(self, request: Request, task_id: Any) -> Response:
        task = self.get_task(task_id)
        serializer = TaskCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        return self.task_response(services.cancel_task(self.actor, task, reason=reason))
