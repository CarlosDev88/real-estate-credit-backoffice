from typing import Any

from rest_framework import serializers

from apps.identity.models import Role
from apps.identity.users import active_partner, role_codes
from apps.partners.models import Partner
from config.serializers import StrictSerializer
from config.validators import validate_e164_phone

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
    role_label = serializers.CharField(
        allow_null=True,
        help_text="Nombre del rol principal (`role`), para mostrar bajo el nombre del usuario; "
        "`null` si no tiene rol.",
    )
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


# --- Usuarios y roles -------------------------------------------------------------------


class UserSerializer(serializers.Serializer):
    """Usuario interno. Nunca expone el hash de la contraseña ni tokens."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    name = serializers.CharField(source="get_full_name")
    phone = serializers.CharField()
    status = serializers.CharField()
    roles = serializers.SerializerMethodField()
    partner = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_roles(self, obj: Any) -> list[str]:
        return role_codes(obj)

    def get_partner(self, obj: Any) -> dict[str, str] | None:
        partner = active_partner(obj)
        return {"id": str(partner.pk), "name": str(partner)} if partner else None


class RoleCodesField(serializers.ListField):
    """Lista de códigos de rol que se resuelve a instancias de ``Role``."""

    child = serializers.CharField(max_length=50)

    def to_internal_value(self, data: Any) -> list[Role]:
        codes = super().to_internal_value(data)
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("Hay roles repetidos.")
        roles = {role.code: role for role in Role.objects.filter(code__in=codes)}
        unknown = [code for code in codes if code not in roles]
        if unknown:
            raise serializers.ValidationError(f"Roles inexistentes: {', '.join(unknown)}.")
        return [roles[code] for code in codes]


def _resolve_partner(value: Any) -> Partner | None:
    if value is None:
        return None
    partner = Partner.objects.filter(pk=value, deleted_at__isnull=True).first()
    if partner is None:
        raise serializers.ValidationError("La constructora no existe.")
    return partner


class UserCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True, default="")
    role_codes = RoleCodesField(allow_empty=False)
    partner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    send_invitation = serializers.BooleanField(required=False, default=True)

    def validate_phone(self, value: str) -> str:
        return validate_e164_phone(value)

    def validate_partner_id(self, value: Any) -> Partner | None:
        return _resolve_partner(value)


class UserUpdateSerializer(StrictSerializer):
    """El correo identifica al usuario y no se edita."""

    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True)

    def validate_phone(self, value: str) -> str:
        return validate_e164_phone(value)


class UserRolesSerializer(StrictSerializer):
    role_codes = RoleCodesField(allow_empty=False)
    partner_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate_partner_id(self, value: Any) -> Partner | None:
        return _resolve_partner(value)


class StatusReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class OptionalStatusReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class UserCreatedSerializer(UserSerializer):
    invitation = serializers.SerializerMethodField()

    def get_invitation(self, obj: Any) -> dict[str, Any] | None:
        invitation = self.context.get("invitation")
        return InvitationSerializer(invitation).data if invitation else None


class PermissionSummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    module = serializers.CharField()
    name = serializers.CharField()


class RoleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    is_active = serializers.BooleanField()
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj: Any) -> list[dict[str, str]]:
        return [
            {
                "code": item.permission.code,
                "module": item.permission.module,
                "name": item.permission.name,
            }
            for item in obj.permission_assignments.all()
        ]
