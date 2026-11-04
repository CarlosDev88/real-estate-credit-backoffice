from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpRequest

from apps.identity.models import (
    AuthSession,
    InternalInvitation,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 0
    autocomplete_fields = ["role"]
    readonly_fields = ["assigned_by", "created_at"]


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "is_active", "last_login", "created_at"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["last_login", "created_at", "updated_at"]
    inlines = [UserRoleInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Estado y permisos de Django admin",
            {"fields": ("is_active", "is_staff", "is_superuser", "deleted_at")},
        ),
        ("Fechas", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    inlines = [RolePermissionInline]


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ["code", "module", "name"]
    list_filter = ["module"]
    search_fields = ["code", "name"]


class ReadOnlyAdmin(admin.ModelAdmin):
    """Registros de seguridad: se consultan, pero no se crean ni editan a mano."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False


@admin.register(AuthSession)
class AuthSessionAdmin(ReadOnlyAdmin):
    list_display = ["user", "created_at", "expires_at", "revoked_at", "ip_address"]
    list_filter = ["revoked_at"]
    search_fields = ["user__email"]
    exclude = ["refresh_token_hash"]


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(ReadOnlyAdmin):
    list_display = ["user", "created_at", "expires_at", "consumed_at", "requested_ip"]
    search_fields = ["user__email"]
    exclude = ["token_hash"]


@admin.register(InternalInvitation)
class InternalInvitationAdmin(ReadOnlyAdmin):
    list_display = ["email", "role", "partner", "status", "expires_at", "created_at"]
    list_filter = ["role"]
    search_fields = ["email"]
    exclude = ["token_hash"]
