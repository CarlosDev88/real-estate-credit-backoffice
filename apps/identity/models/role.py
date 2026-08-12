import uuid

from django.conf import settings
from django.db import models


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "roles"

    def __str__(self) -> str:
        return self.name


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(max_length=100, unique=True)
    module = models.CharField(max_length=50)
    name = models.CharField(max_length=120)

    description = models.TextField(blank=True)

    class Meta:
        db_table = "permissions"

    def __str__(self) -> str:
        return self.code


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    # user_id foreing key
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_role_assignments"
    )

    # role_id foreing key
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="user_assignments")

    # assigned_by_id foreing key
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments_made",
    )

    class Meta:
        db_table = "user_roles"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_roles_user_role")
        ]


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    # role_id foreing key
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permission_assignments")

    # permission_id
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="uq_role_permissions_role_permission",
            )
        ]
