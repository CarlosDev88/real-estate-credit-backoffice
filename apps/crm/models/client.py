import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q


class Client(models.Model):
    """Persona compradora o participante de una solicitud. Existe una sola vez.

    No es un usuario interno: no inicia sesión con contraseña. Su acceso al portal
    será por enlace mágico (paso 9).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Ítem del catálogo `identity_document_type` (CC, CE, PA, PPT).
    document_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Número normalizado: sin espacios, puntos ni guiones, en mayúsculas.
    document_number = models.CharField(max_length=30)
    first_names = models.CharField(max_length=120)
    last_names = models.CharField(max_length=120)
    birth_date = models.DateField(null=True, blank=True)
    # Dato de contacto; no se usa para iniciar sesión.
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Ítem del catálogo `lead_origin`.
    origin_item = models.ForeignKey(
        "catalogs.CatalogItem",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_created",
    )
    # Archivo o anonimización futura.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "clients"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_type_item", "document_number"], name="uq_clients_document"
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_names} {self.last_names}".strip()


class ClientAddress(models.Model):
    """Dirección de contacto de un cliente (no es el inmueble financiado)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="addresses")
    # Ítem del catálogo `address_type`.
    address_type_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    # Ítem del catálogo `municipality`.
    city_item = models.ForeignKey(
        "catalogs.CatalogItem", on_delete=models.RESTRICT, related_name="+"
    )
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=12, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "client_addresses"
        ordering = ["-is_primary", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(is_primary=True),
                name="uq_client_addresses_primary",
            ),
        ]

    def __str__(self) -> str:
        return self.line1
