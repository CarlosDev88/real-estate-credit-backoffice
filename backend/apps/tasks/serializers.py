from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogs.fields import CatalogItemCodeField
from apps.catalogs.serializers import CatalogItemRefSerializer
from apps.crm.serializers import UserRefSerializer
from apps.tasks import services
from apps.tasks.models import PRIORITY_CATALOG, Task, TaskParentType, TaskSource, TaskStatus
from config.serializers import ChoiceLabelField, StrictSerializer


class TaskParentSerializer(serializers.Serializer):
    """Solicitud u oportunidad de la tarea. Las oportunidades no tienen código: ``code``
    es nulo y ``client_display_name`` las identifica."""

    type = serializers.ChoiceField(choices=TaskParentType.choices)
    type_label = ChoiceLabelField(TaskParentType, source="type")
    id = serializers.UUIDField()
    code = serializers.CharField(allow_null=True)
    client_display_name = serializers.CharField()


class TaskSerializer(serializers.ModelSerializer):
    status_label = ChoiceLabelField(TaskStatus, source="status")
    source_label = ChoiceLabelField(TaskSource, source="source")
    priority = CatalogItemRefSerializer(source="priority_item")
    assigned_to = UserRefSerializer()
    created_by = UserRefSerializer(allow_null=True)
    # `parent` choca con el atributo `Field.parent` de los stubs de DRF.
    parent = serializers.SerializerMethodField()  # type: ignore[assignment]
    is_overdue = serializers.SerializerMethodField(
        help_text="Pendiente y con `due_at` antes de hoy (fecha de Bogotá), como `due=overdue`."
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "status_label",
            "priority",
            "source",
            "source_label",
            "assigned_to",
            "created_by",
            "parent",
            "due_at",
            "is_overdue",
            "completed_at",
            "cancelled_at",
            "cancel_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(TaskParentSerializer)
    def get_parent(self, obj: Task) -> dict[str, Any]:
        if obj.application is not None:
            parent = {
                "type": TaskParentType.APPLICATION,
                "id": obj.application.pk,
                "code": obj.application.code,
                "client_display_name": obj.application.opportunity.client.full_name,
            }
        else:
            assert obj.opportunity is not None
            parent = {
                "type": TaskParentType.OPPORTUNITY,
                "id": obj.opportunity.pk,
                "code": None,
                "client_display_name": obj.opportunity.client.full_name,
            }
        return dict(TaskParentSerializer(parent).data)

    def get_is_overdue(self, obj: Task) -> bool:
        return services.is_overdue(obj)


class TaskCreateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    application_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    opportunity_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    assigned_to_id = serializers.UUIDField(
        required=False, allow_null=True, default=None, help_text="Por omisión, el actor."
    )
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    priority_code = CatalogItemCodeField(
        catalog_code=PRIORITY_CATALOG, required=False, help_text="Por omisión, `MEDIUM`."
    )


class TaskUpdateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=180, required=False)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    assigned_to_id = serializers.UUIDField(required=False)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    priority_code = CatalogItemCodeField(catalog_code=PRIORITY_CATALOG, required=False)


class TaskCancelSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)
