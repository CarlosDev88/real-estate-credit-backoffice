import uuid
from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuthSession(models.Model):
    """Sesión interna respaldada por un refresh token opaco y rotativo.

    Solo se guarda el hash SHA-256 del refresh token. Cada rotación crea una
    sesión nueva enlazada con ``rotated_from`` y revoca la anterior, lo que
    permite detectar la reutilización de un token ya rotado.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_sessions",
    )

    refresh_token_hash = models.CharField(max_length=64, unique=True)

    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    # Relación uno a uno: cada sesión rota como máximo una vez.
    rotated_from = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rotated_to",
    )

    ip_address = models.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        null=True,
        blank=True,
    )

    user_agent_summary = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "auth_sessions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="ck_auth_sessions_expiry",
            )
        ]
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="ix_auth_sessions_user_revoked"),
        ]

    def __str__(self) -> str:
        return f"Sesión {self.id} de {self.user_id}"

    def is_active_at(self, moment: datetime | None = None) -> bool:
        moment = moment or timezone.now()
        return self.revoked_at is None and self.expires_at > moment


class PasswordResetToken(models.Model):
    """Token de un solo uso para restablecer la contraseña de un usuario interno."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )

    token_hash = models.CharField(max_length=64, unique=True)

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    requested_ip = models.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "password_reset_tokens"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="ck_password_reset_expiry",
            )
        ]

    def __str__(self) -> str:
        return f"Token de recuperación {self.id} de {self.user_id}"

    def is_usable_at(self, moment: datetime | None = None) -> bool:
        moment = moment or timezone.now()
        return self.consumed_at is None and self.expires_at > moment
