import uuid
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q

from apps.catalogs.workflow import FlowType

if TYPE_CHECKING:
    from apps.identity.models import Role


class WorkflowTransition(models.Model):
    """Acción permitida entre dos estados estructurales de un flujo."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    flow_type = models.CharField(max_length=30, choices=FlowType.choices)
    code = models.CharField(max_length=80)
    from_status = models.CharField(max_length=40)
    to_status = models.CharField(max_length=40)
    label = models.CharField(max_length=120)

    required_permission = models.ForeignKey(
        "identity.Permission",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="workflow_transitions",
    )
    guard_code = models.CharField(max_length=80, blank=True)
    # Se crea inactiva; solo quien tiene `workflow.publish` la habilita.
    is_active = models.BooleanField(default=False)
    # True: solo la ejecuta el servicio de su módulo (por ejemplo, la radicación o una
    # respuesta del banco). `POST /status-transitions` la rechaza (`409`) y las acciones
    # disponibles no la listan.
    system_only = models.BooleanField(default=False, db_default=False)

    roles: "models.ManyToManyField[Role, WorkflowTransitionRole]" = models.ManyToManyField(
        "identity.Role",
        through="WorkflowTransitionRole",
        related_name="workflow_transitions",
    )

    class Meta:
        db_table = "workflow_transitions"
        ordering = ["flow_type", "from_status", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["flow_type", "code"], name="uq_workflow_transitions_flow_code"
            ),
            models.CheckConstraint(
                condition=Q(flow_type__in=FlowType.values),
                name="ck_workflow_transitions_flow",
            ),
            models.CheckConstraint(
                condition=~Q(from_status=models.F("to_status")),
                name="ck_workflow_transitions_states",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.flow_type}:{self.code}"


class WorkflowTransitionRole(models.Model):
    """Rol autorizado para ejecutar una transición (tabla puente N:M)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    transition = models.ForeignKey(
        WorkflowTransition, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(
        "identity.Role",
        on_delete=models.CASCADE,
        related_name="workflow_transition_assignments",
    )

    class Meta:
        db_table = "workflow_transition_roles"
        constraints = [
            models.UniqueConstraint(
                fields=["transition", "role"], name="uq_workflow_transition_roles"
            )
        ]
