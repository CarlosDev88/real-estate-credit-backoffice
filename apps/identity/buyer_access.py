"""Enlaces de acceso del comprador (API §8): emisión, listado y revocación.

Está separado de ``services.py`` porque depende de ``applications``, y ``applications``
depende de ``identity.services``.

Reglas (``specs/TAREA-buyer-access.md``, decisiones 1 a 8):

- El enlace es siempre para el titular (`PRIMARY`) activo; la entrada no elige cliente.
- Se emite en cualquier estado no terminal, también después de `FILED`.
- Emitir revoca los enlaces pendientes de la misma solicitud, pero no cierra las
  sesiones vivas.
- El token en claro solo existe en la respuesta de la emisión y en el correo. En la
  base se guarda su hash, y nunca se escribe en los logs.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.applications.exceptions import ApplicationClosed
from apps.applications.models import ApplicationParticipant, CreditApplication, ParticipantRole
from apps.applications.services import applications_visible_to, get_application_scope
from apps.catalogs.models import CatalogItem
from apps.crm.models import Client
from apps.identity.emails import build_buyer_access_url, send_buyer_access_email
from apps.identity.models import (
    BuyerAccessLink,
    BuyerAccessLinkStatus,
    BuyerSession,
    User,
    buyer_access_link_status_filter,
)
from apps.identity.tokens import generate_opaque_token, hash_token

logger = logging.getLogger(__name__)

CHANNEL_CATALOG = "buyer_access_channel"
COPY_LINK = "COPY_LINK"
EMAIL = "EMAIL"


@dataclass(frozen=True)
class IssuedLink:
    link: BuyerAccessLink
    # Lleva el token en claro: solo viaja en la respuesta `201`.
    url: str


def links_queryset() -> QuerySet[BuyerAccessLink]:
    return BuyerAccessLink.objects.select_related("created_by", "delivery_channel_item", "session")


def links_visible_to(user: User) -> QuerySet[BuyerAccessLink]:
    """Enlaces de las solicitudes que ``user`` ve (mismo alcance que la solicitud)."""
    return links_queryset().filter(application_id__in=applications_visible_to(user).values("pk"))


def default_channel() -> CatalogItem:
    return CatalogItem.objects.get(catalog__code=CHANNEL_CATALOG, code=COPY_LINK)


def _primary_client(application: CreditApplication) -> Client:
    participant = ApplicationParticipant.objects.select_related("client").get(
        application=application, role=ParticipantRole.PRIMARY, is_active=True
    )
    return participant.client


def issue_access_link(
    actor: User,
    application: CreditApplication,
    *,
    channel: CatalogItem,
    expires_in_hours: int,
) -> IssuedLink:
    """Emite un enlace para el titular y revoca los pendientes anteriores.

    - Solicitud terminada: ``409 APPLICATION_CLOSED``.
    - Canal `EMAIL` sin correo del titular: ``400`` en ``delivery_channel``.
    """
    raw_token = generate_opaque_token()
    with transaction.atomic():
        # Bloquea la solicitud: dos emisiones simultáneas no dejan dos enlaces pendientes.
        locked = CreditApplication.objects.select_for_update().get(pk=application.pk)
        if locked.is_terminal:
            raise ApplicationClosed()
        client = _primary_client(locked)
        if channel.code == EMAIL and not client.email:
            raise ValidationError(
                {"delivery_channel": ["El titular no tiene un correo registrado."]}
            )

        now = timezone.now()
        BuyerAccessLink.objects.filter(
            buyer_access_link_status_filter(BuyerAccessLinkStatus.PENDING, now),
            application=locked,
        ).update(revoked_at=now)
        link = BuyerAccessLink.objects.create(
            client=client,
            application=locked,
            token_hash=hash_token(raw_token),
            created_by=actor,
            delivery_channel_item=channel,
            expires_at=now + timedelta(hours=expires_in_hours),
        )
        if channel.code == EMAIL:
            transaction.on_commit(
                lambda: send_buyer_access_email(client=client, link=link, raw_token=raw_token)
            )

    logger.info(
        "Enlace de comprador %s emitido para la solicitud %s por %s (%s)",
        link.pk,
        locked.code,
        actor.pk,
        channel.code,
    )
    return IssuedLink(link=link, url=build_buyer_access_url(raw_token))


def ensure_can_revoke(actor: User, link: BuyerAccessLink) -> None:
    """El broker solo revoca los enlaces que él emitió (``403``)."""
    if get_application_scope(actor).is_restricted and link.created_by_id != actor.pk:
        raise PermissionDenied("Solo puedes revocar los enlaces que generaste.")


def revoke_access_link(actor: User, link: BuyerAccessLink) -> None:
    """Corta el acceso que da el enlace. Es idempotente.

    - `PENDING`: se revoca el enlace.
    - `CONSUMED`: el ``CHECK`` del esquema no admite revocar un enlace consumido, así
      que se revoca la sesión que nació de él.
    - `REVOKED` o `EXPIRED`: no hay nada que cortar.
    """
    ensure_can_revoke(actor, link)
    with transaction.atomic():
        locked = BuyerAccessLink.objects.select_for_update().get(pk=link.pk)
        now = timezone.now()
        status = locked.status_at(now)
        if status == BuyerAccessLinkStatus.PENDING:
            locked.revoked_at = now
            locked.save(update_fields=["revoked_at"])
        elif status == BuyerAccessLinkStatus.CONSUMED:
            BuyerSession.objects.filter(access_link=locked, revoked_at__isnull=True).update(
                revoked_at=now
            )
        else:
            return
    logger.info("Acceso del enlace de comprador %s revocado por %s", link.pk, actor.pk)
