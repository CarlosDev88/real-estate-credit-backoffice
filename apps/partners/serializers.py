from typing import Any

from rest_framework import serializers

from apps.catalogs.fields import CatalogItemCodeField
from apps.identity.models import User
from apps.partners.models import Partner, PartnerMembership, PartnerStatus, Project
from apps.partners.validators import normalize_nit
from config.serializers import StrictSerializer
from config.validators import validate_e164_phone

REASON_MAX_LENGTH = 1000


class UserSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="get_full_name")
    email = serializers.EmailField()


class UserReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="get_full_name")


# --- Constructoras ----------------------------------------------------------------------


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = [
            "id",
            "legal_name",
            "trade_name",
            "tax_id",
            "status",
            "contact_name",
            "contact_email",
            "contact_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PartnerMetricsSerializer(serializers.Serializer):
    projects_by_status = serializers.DictField(child=serializers.IntegerField())
    active_members = serializers.IntegerField()


class PartnerDetailSerializer(PartnerSerializer):
    metrics = serializers.SerializerMethodField()

    class Meta(PartnerSerializer.Meta):
        fields = [*PartnerSerializer.Meta.fields, "metrics"]
        read_only_fields = fields

    def get_metrics(self, obj: Partner) -> dict[str, Any]:
        return self.context["metrics"]


class _PartnerContactFields(StrictSerializer):
    trade_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    contact_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    contact_email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=25, required=False, allow_blank=True)

    def validate_contact_phone(self, value: str) -> str:
        return validate_e164_phone(value)


class PartnerCreateSerializer(_PartnerContactFields):
    legal_name = serializers.CharField(max_length=180)
    tax_id = serializers.CharField(max_length=30)

    def validate_tax_id(self, value: str) -> str:
        return normalize_nit(value)


class PartnerUpdateSerializer(_PartnerContactFields):
    """El NIT identifica a la constructora y no se edita."""

    legal_name = serializers.CharField(max_length=180, required=False)


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=REASON_MAX_LENGTH)


class OptionalReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=REASON_MAX_LENGTH, required=False, allow_blank=True)


# --- Membresías -------------------------------------------------------------------------


class MembershipSerializer(serializers.ModelSerializer):
    partner_id = serializers.UUIDField(read_only=True)
    partner_name = serializers.CharField(source="partner.__str__", read_only=True)
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = PartnerMembership
        fields = [
            "id",
            "partner_id",
            "partner_name",
            "user",
            "job_title",
            "status",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MembershipCreateSerializer(StrictSerializer):
    """Agrega un usuario existente (`user_id`) o invita a uno nuevo (`email`).

    Con `email` se crea una invitación de rol CONSTRUCTION_PARTNER; la membresía se
    crea cuando la persona acepta. `job_title` y `started_at` solo aplican con
    `user_id` (la invitación no los guarda).
    """

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    email = serializers.EmailField(max_length=254, required=False, allow_null=True, default=None)
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    started_at = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_user_id(self, value: Any) -> User | None:
        if value is None:
            return None
        user = User.objects.filter(pk=value, deleted_at__isnull=True).first()
        if user is None:
            raise serializers.ValidationError("El usuario no existe.")
        return user

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        has_user, has_email = attrs["user_id"] is not None, attrs["email"] is not None
        if has_user == has_email:
            raise serializers.ValidationError(
                {"user_id": ["Envía `user_id` para un usuario existente o `email` para invitar."]}
            )
        if has_email and (attrs["job_title"] or attrs["started_at"]):
            raise serializers.ValidationError(
                {"job_title": ["El cargo y la fecha de inicio solo aplican con `user_id`."]}
            )
        return attrs


class MembershipUpdateSerializer(StrictSerializer):
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=PartnerStatus.choices, required=False)


# --- Proyectos --------------------------------------------------------------------------


class PartnerReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="__str__")


class CitySerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    department_code = serializers.CharField(source="parent_item.code", allow_null=True)
    department_label = serializers.CharField(source="parent_item.label", allow_null=True)


class ProjectSerializer(serializers.ModelSerializer):
    partner = PartnerReferenceSerializer(read_only=True)
    city = CitySerializer(source="city_item", read_only=True)
    created_by = UserReferenceSerializer(read_only=True)
    validated_by = UserReferenceSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "partner",
            "name",
            "code",
            "status",
            "city",
            "address",
            "description",
            "estimated_delivery_date",
            "created_by",
            "validated_by",
            "validated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProjectDetailSerializer(ProjectSerializer):
    available_actions = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = [*ProjectSerializer.Meta.fields, "available_actions"]
        read_only_fields = fields

    def get_available_actions(self, obj: Project) -> list[str]:
        return self.context["available_actions"]


class _ProjectFields(StrictSerializer):
    code = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    city_code = CatalogItemCodeField(catalog_code="municipality", required=False)
    address = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    estimated_delivery_date = serializers.DateField(required=False, allow_null=True)

    def validate_code(self, value: str | None) -> str | None:
        # Un código vacío equivale a no tener código (varios proyectos pueden no tenerlo).
        if not value:
            return None
        return value.strip() or None

    def to_service_data(self) -> dict[str, Any]:
        data = dict(self.validated_data)
        if "city_code" in data:
            data["city_item"] = data.pop("city_code")
        return data


class ProjectCreateSerializer(_ProjectFields):
    name = serializers.CharField(max_length=180)
    partner_id = serializers.UUIDField(required=False, allow_null=True)
    city_code = CatalogItemCodeField(catalog_code="municipality")
    address = serializers.CharField(max_length=255)


class ProjectUpdateSerializer(_ProjectFields):
    name = serializers.CharField(max_length=180, required=False)
