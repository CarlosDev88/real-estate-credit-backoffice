from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.activity.models import ActivityEventType, ActivityLog
from apps.crm.serializers import UserRefSerializer
from config.serializers import ChoiceLabelField, StrictSerializer

# Actor de las filas creadas desde el portal, como lo ve el backoffice.
BUYER_PORTAL_ACTOR = "Portal del comprador"
# Actor como lo ve el comprador.
BUYER_SELF_ACTOR = "Tú"
BUYER_ADVISOR_ACTOR = "Tu asesor"


class ActivityActorSerializer(serializers.Serializer):
    name = serializers.CharField()


class ActivitySerializer(serializers.ModelSerializer):
    """Fila de la línea de tiempo. ``actor`` es ``{name}`` o nulo (un evento del sistema).
    Con ``context["buyer"]``, el actor se muestra como "Tú" o "Tu asesor"."""

    event_type_label = ChoiceLabelField(ActivityEventType, source="event_type")
    actor = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "event_type", "event_type_label", "title", "message", "actor", "created_at"]
        read_only_fields = fields

    @extend_schema_field(ActivityActorSerializer(allow_null=True))
    def get_actor(self, obj: ActivityLog) -> dict[str, Any] | None:
        buyer = self.context.get("buyer", False)
        if obj.actor_buyer_session_id is not None:
            name = BUYER_SELF_ACTOR if buyer else BUYER_PORTAL_ACTOR
        elif obj.actor_user is not None:
            name = BUYER_ADVISOR_ACTOR if buyer else obj.actor_user.get_full_name()
        else:
            return None
        return {"name": name}


class NoteSerializer(serializers.ModelSerializer):
    body = serializers.CharField(source="message")
    author = UserRefSerializer(source="actor_user", allow_null=True)

    class Meta:
        model = ActivityLog
        fields = ["id", "body", "author", "created_at"]
        read_only_fields = fields


class NoteCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=2000)
