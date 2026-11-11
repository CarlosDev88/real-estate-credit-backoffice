"""Edición del expediente por el comprador (``specs/TAREA-buyer-access.md``, Parte 5).

- Alcance: los participantes activos de la solicitud de la sesión, sus perfiles
  financieros y sus fuentes de ingreso. Cualquier otro recurso responde ``404``.
- Datos personales: solo los del titular (``email``, ``phone``, ``birth_date`` y
  direcciones). Nombres y documento los corrige el asesor.
- Concurrencia y estado: los mismos de los servicios internos (``lock_for_edit``):
  ``409 STALE_VERSION`` y ``409 APPLICATION_NOT_EDITABLE`` después de `FILED`. Con la
  solicitud terminada, las vistas responden antes ``409 APPLICATION_CLOSED``
  (``ApplicationNotClosed``, decisión 5).

Las mutaciones de perfil e ingresos reutilizan los servicios de ``applications`` con la
sesión como actor.
"""

import logging
import uuid
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from apps.applications.models import (
    ApplicationParticipant,
    CreditApplication,
    FinancialProfile,
    IncomeSource,
)
from apps.applications.services import (
    bump_version,
    financial_profiles_queryset,
    income_sources_queryset,
    lock_for_edit,
    participants_queryset,
)
from apps.applications.signals import application_updated
from apps.crm.models import Client, ClientAddress
from apps.identity.models import BuyerSession

logger = logging.getLogger(__name__)

ADDRESS_FIELDS = ("address_type_item", "city_item", "line1", "line2", "postal_code")


# --- Alcance ----------------------------------------------------------------------------


def buyer_participants(session: BuyerSession) -> QuerySet[ApplicationParticipant]:
    """Participantes activos de la solicitud: el titular y los co-solicitantes (decisión 18)."""
    return (
        participants_queryset()
        .filter(application_id=session.application_id, is_active=True)
        .order_by("created_at")
    )


def buyer_financial_profiles(session: BuyerSession) -> QuerySet[FinancialProfile]:
    return financial_profiles_queryset().filter(
        participant__application_id=session.application_id, participant__is_active=True
    )


def buyer_income_sources(session: BuyerSession) -> QuerySet[IncomeSource]:
    return income_sources_queryset().filter(
        financial_profile__participant__application_id=session.application_id,
        financial_profile__participant__is_active=True,
    )


def buyer_client(session: BuyerSession) -> Client:
    return Client.objects.select_related("document_type_item").get(pk=session.client_id)


def client_addresses(client: Client) -> QuerySet[ClientAddress]:
    return client.addresses.select_related("address_type_item", "city_item")


# --- Datos personales -------------------------------------------------------------------


def _address_errors(items: list[dict[str, Any]], existing: set[uuid.UUID]) -> dict[str, Any]:
    errors: dict[str, Any] = {}
    seen: set[uuid.UUID] = set()
    for index, item in enumerate(items):
        address_id = item.get("id")
        if address_id is None:
            continue
        if address_id not in existing:
            errors[f"addresses[{index}].id"] = ["La dirección no es del titular."]
        elif address_id in seen:
            errors[f"addresses[{index}].id"] = ["La dirección está repetida."]
        seen.add(address_id)
    if sum(bool(item.get("is_primary")) for item in items) > 1:
        errors["addresses"] = ["Solo una dirección puede ser la principal."]
    return errors


def _replace_addresses(client: Client, items: list[dict[str, Any]]) -> bool:
    """Deja exactamente las direcciones de ``items``. Devuelve si algo cambió.

    Una dirección con ``id`` se actualiza, una sin ``id`` se crea y las que no llegan se
    eliminan. Si ninguna viene como principal, la primera lo es.
    """
    existing = {address.pk: address for address in client.addresses.select_for_update()}
    errors = _address_errors(items, set(existing))
    if errors:
        raise ValidationError(errors)

    changed = False
    keep = {item["id"] for item in items if item.get("id") is not None}
    removed = [pk for pk in existing if pk not in keep]
    if removed:
        ClientAddress.objects.filter(pk__in=removed).delete()
        changed = True

    primary_index = next((i for i, item in enumerate(items) if item.get("is_primary")), 0)
    primary: ClientAddress | None = None
    for index, item in enumerate(items):
        values = {field: item[field] for field in ADDRESS_FIELDS}
        address = existing.get(item["id"]) if item.get("id") is not None else None
        if address is None:
            address = ClientAddress.objects.create(client=client, is_primary=False, **values)
            changed = True
        else:
            diff = [field for field, value in values.items() if getattr(address, field) != value]
            if diff:
                for field in diff:
                    setattr(address, field, values[field])
                address.save(update_fields=[*diff, "updated_at"])
                changed = True
        if index == primary_index:
            primary = address

    if primary is not None and not primary.is_primary:
        # Índice único parcial: primero se desmarca la principal anterior.
        client.addresses.filter(is_primary=True).update(is_primary=False)
        ClientAddress.objects.filter(pk=primary.pk).update(is_primary=True)
        changed = True
    return changed


def update_buyer_profile(
    session: BuyerSession,
    *,
    expected_version: int,
    changes: dict[str, Any],
    addresses: list[dict[str, Any]] | None,
) -> bool:
    """Actualiza los datos de contacto del titular. Devuelve si algo cambió.

    ``addresses``, si llega, reemplaza la lista completa. Un cambio real aumenta la
    versión de la solicitud, que es la que viaja en ``If-Match``.
    """
    with transaction.atomic():
        locked = lock_for_edit(session.application_id, expected_version)
        client = Client.objects.select_for_update().get(pk=session.client_id)
        changed = [field for field, value in changes.items() if getattr(client, field) != value]
        for field in changed:
            setattr(client, field, changes[field])
        if changed:
            client.save(update_fields=[*changed, "updated_at"])
        addresses_changed = addresses is not None and _replace_addresses(client, addresses)
        if not changed and not addresses_changed:
            return False
        bump_version(locked)

    fields = [*changed, *(["addresses"] if addresses_changed else [])]
    logger.info(
        "Datos del titular de %s actualizados por la sesión de comprador %s: %s",
        locked.code,
        session.pk,
        ", ".join(fields),
    )
    application_updated.send(
        sender=CreditApplication, application=locked, fields=["client"], actor=session
    )
    return True
