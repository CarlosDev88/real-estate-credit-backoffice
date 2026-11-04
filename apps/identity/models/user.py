import uuid
from typing import Any, cast

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        """Normaliza el correo completo a minúsculas.

        El esquema define ``email`` como CITEXT: dos correos que solo difieren en
        mayúsculas son el mismo usuario. Guardarlo siempre en minúsculas, junto con
        el índice único sobre ``LOWER(email)``, mantiene esa garantía.
        """
        return (email or "").strip().lower()

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        if not email:
            raise ValueError("El correo es obligatorio.")
        email = self.normalize_email(email)
        user = cast("User", self.model(email=email, **extra_fields))
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # type: ignore[assignment]
    # `created_at` reemplaza a `date_joined` de Django (ver migración 0003).
    date_joined = None  # type: ignore[assignment]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)

    # Borrado lógico: un usuario eliminado conserva su historial, pero no inicia sesión.
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()  # type: ignore[misc, assignment]

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uq_users_email_lower"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def can_authenticate(self) -> bool:
        return self.is_active and self.deleted_at is None
