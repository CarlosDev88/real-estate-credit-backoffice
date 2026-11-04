from typing import Any

from rest_framework import serializers

from apps.identity.models import Role
from apps.partners.models import Partner
from config.serializers import StrictSerializer

PASSWORD_MAX_LENGTH = 128


def password_field() -> serializers.CharField:
    return serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        trim_whitespace=False,
        write_only=True,
        style={"input_type": "password"},
    )


# --- Entradas -------------------------------------------------------------------------


class LoginSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    password = password_field()


class PasswordResetRequestSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(StrictSerializer):
    token = serializers.CharField(max_length=128, write_only=True)
    new_password = password_field()


class ChangePasswordSerializer(StrictSerializer):
    current_password = password_field()
    new_password = password_field()


# --- Salidas --------------------------------------------------------------------------


class LoginUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField(allow_null=True)


class LoginResponseSerializer(serializers.Serializer):
    user = LoginUserSerializer()
    permissions = serializers.ListField(child=serializers.CharField())
    session_expires_at = serializers.DateTimeField()


class RefreshResponseSerializer(serializers.Serializer):
    session_expires_at = serializers.DateTimeField()


class ScopeSerializer(serializers.Serializer):
    assigned_applications_only = serializers.BooleanField()
    partner_id = serializers.UUIDField(allow_null=True)


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())
    permissions = serializers.ListField(child=serializers.CharField())
    scope = ScopeSerializer()


class AcceptedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


# --- Invitaciones internas --------------------------------------------------------------


class InvitationSerializer(serializers.Serializer):
    """Nunca expone el token ni su hash."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    role = serializers.CharField(source="role.code")
    partner = serializers.SerializerMethodField()
    invited_by = serializers.SerializerMethodField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField()
    consumed_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_partner(self, obj: Any) -> dict[str, str] | None:
        if obj.partner is None:
            return None
        return {"id": str(obj.partner.pk), "name": str(obj.partner)}

    def get_invited_by(self, obj: Any) -> dict[str, str] | None:
        if obj.invited_by is None:
            return None
        return {"id": str(obj.invited_by.pk), "name": obj.invited_by.get_full_name()}


class InvitationCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.CharField(max_length=50)
    partner_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate_role(self, value: str) -> Role:
        role = Role.objects.filter(code=value).first()
        if role is None:
            raise serializers.ValidationError("El rol no existe.")
        return role

    def validate_partner_id(self, value: Any) -> Partner | None:
        if value is None:
            return None
        partner = Partner.objects.filter(pk=value, deleted_at__isnull=True).first()
        if partner is None:
            raise serializers.ValidationError("La constructora no existe.")
        return partner


class InvitationAcceptSerializer(StrictSerializer):
    token = serializers.CharField(max_length=128, write_only=True)
    password = password_field()
    password_confirmation = password_field()
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class AcceptedUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
