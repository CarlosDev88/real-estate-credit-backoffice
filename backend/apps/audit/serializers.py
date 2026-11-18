from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.actions import AuditAction, AuditResult
from apps.audit.models import AuditEvent
from config.serializers import ChoiceLabelField


class AuditActorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


def buyer_actor_name(session_id: Any) -> str:
    return f"Comprador (sesión {str(session_id)[:8]})"


class AuditEventSerializer(serializers.ModelSerializer):
    action_label = ChoiceLabelField(AuditAction, source="action")
    result_label = ChoiceLabelField(AuditResult, source="result")
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "action",
            "action_label",
            "result",
            "result_label",
            "resource_type",
            "resource_id",
            "actor",
            "request_id",
            "ip_address",
            "metadata",
        ]
        read_only_fields = fields

    @extend_schema_field(AuditActorSerializer(allow_null=True))
    def get_actor(self, obj: AuditEvent) -> dict[str, Any] | None:
        """El usuario interno (``{id, name}``) o la sesión del comprador. Nulo si no hubo
        actor (un intento anónimo, un comando) o si ya no existe."""
        if obj.actor_user is not None:
            return {"id": str(obj.actor_user.pk), "name": obj.actor_user.get_full_name()}
        if obj.actor_buyer_session_id is not None:
            session_id = obj.actor_buyer_session_id
            return {"id": str(session_id), "name": buyer_actor_name(session_id)}
        return None
