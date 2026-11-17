from rest_framework import serializers

from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
)
from config.serializers import ChoiceLabelField


class BuyerNotificationSerializer(serializers.ModelSerializer):
    notification_type_label = ChoiceLabelField(NotificationType, source="notification_type")

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "notification_type_label",
            "title",
            "message",
            "created_at",
            "read_at",
        ]
        read_only_fields = fields


class BuyerNotificationFilterSerializer(serializers.Serializer):
    unread = serializers.BooleanField(required=False, default=False)


class NotificationCountSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)


class NotificationDeliverySerializer(serializers.ModelSerializer):
    channel_label = ChoiceLabelField(DeliveryChannel, source="channel")
    status_label = ChoiceLabelField(DeliveryStatus, source="status")

    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "channel",
            "channel_label",
            "destination",
            "status",
            "status_label",
            "attempt_count",
            "next_attempt_at",
            "sent_at",
            "last_error_code",
        ]
        read_only_fields = fields


class ApplicationNotificationSerializer(BuyerNotificationSerializer):
    deliveries = NotificationDeliverySerializer(many=True, read_only=True)

    class Meta(BuyerNotificationSerializer.Meta):
        fields = [*BuyerNotificationSerializer.Meta.fields, "deliveries"]
        read_only_fields = fields
