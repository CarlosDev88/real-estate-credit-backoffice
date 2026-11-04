from rest_framework import serializers

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
