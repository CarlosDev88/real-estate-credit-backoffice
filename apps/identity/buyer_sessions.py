"""Sesión temporal del comprador (API §8): consumo del enlace, validación y cierre.

Reglas (``specs/TAREA-buyer-access.md``, decisiones 5, 6 y 9):

- El enlace sirve una sola vez. El consumo bloquea su fila, así que de dos consumos
  simultáneos solo uno abre sesión.
- Consumir revoca las otras sesiones vivas del mismo cliente y solicitud.
- La sesión dura ``BUYER_SESSION_LIFETIME`` desde el consumo y no se renueva.
- La sesión solo da acceso mientras su cliente siga siendo el titular activo.
- Ni el token del enlace ni el de la sesión se escriben en los logs. En la base solo
  se guarda su hash.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.applications.models import ApplicationParticipant, ParticipantRole
from apps.identity.exceptions import (
    MagicLinkConsumed,
    MagicLinkExpired,
    MagicLinkInvalid,
    MagicLinkRevoked,
)
from apps.identity.models import BuyerAccessLink, BuyerAccessLinkStatus, BuyerSession
from apps.identity.services import client_ip, user_agent_summary
from apps.identity.tokens import generate_opaque_token, hash_token

logger = logging.getLogger(__name__)

# `generate_opaque_token()` produce 43 caracteres base64url. El margen admite tokens de
# otra longitud sin aceptar entradas arbitrarias.
_TOKEN_FORMAT = re.compile(r"[A-Za-z0-9_-]{16,128}")

# `last_seen_at` se escribe como máximo una vez por este intervalo.
LAST_SEEN_RESOLUTION = timedelta(minutes=1)


@dataclass(frozen=True)
class IssuedBuyerSession:
    session: BuyerSession
    # Token en claro: solo viaja en la cookie de la respuesta del consumo.
    token: str

    @property
    def expires_at(self) -> datetime:
        return self.session.expires_at


def is_active_primary(application_id: uuid.UUID, client_id: uuid.UUID) -> bool:
    """El cliente sigue siendo el titular activo de la solicitud."""
    return ApplicationParticipant.objects.filter(
        application_id=application_id,
        client_id=client_id,
        role=ParticipantRole.PRIMARY,
        is_active=True,
    ).exists()


def _ensure_link_usable(link: BuyerAccessLink | None, moment: datetime) -> BuyerAccessLink:
    if link is None:
        raise MagicLinkInvalid()
    status = link.status_at(moment)
    if status == BuyerAccessLinkStatus.CONSUMED:
        raise MagicLinkConsumed()
    if status == BuyerAccessLinkStatus.REVOKED:
        raise MagicLinkRevoked()
    if status == BuyerAccessLinkStatus.EXPIRED:
        raise MagicLinkExpired()
    # Un enlace vigente que ya no da acceso no se consume: queda pendiente hasta
    # vencer o hasta que lo revoquen.
    if link.application.is_terminal or not is_active_primary(link.application_id, link.client_id):
        raise MagicLinkInvalid()
    return link


def consume_access_link(*, request: HttpRequest, raw_token: str) -> IssuedBuyerSession:
    """Consume el enlace y abre la sesión del comprador.

    Errores (``401``): ``MAGIC_LINK_INVALID``, ``MAGIC_LINK_EXPIRED``,
    ``MAGIC_LINK_CONSUMED`` y ``MAGIC_LINK_REVOKED``.
    """
    if not _TOKEN_FORMAT.fullmatch(raw_token):
        raise MagicLinkInvalid()

    session_token = generate_opaque_token()
    with transaction.atomic():
        now = timezone.now()
        link = _ensure_link_usable(
            BuyerAccessLink.objects.select_for_update(of=("self",))
            .select_related("application")
            .filter(token_hash=hash_token(raw_token))
            .first(),
            now,
        )
        link.consumed_at = now
        link.save(update_fields=["consumed_at"])
        # Una sola sesión viva por cliente y solicitud.
        BuyerSession.objects.filter(
            application_id=link.application_id,
            client_id=link.client_id,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        session = BuyerSession.objects.create(
            access_link=link,
            client_id=link.client_id,
            application_id=link.application_id,
            session_token_hash=hash_token(session_token),
            expires_at=now + settings.BUYER_SESSION_LIFETIME,
            last_seen_at=now,
            ip_address=client_ip(request),
            user_agent_summary=user_agent_summary(request),
        )

    logger.info(
        "Enlace de comprador %s consumido: sesión %s para la solicitud %s",
        link.pk,
        session.pk,
        link.application.code,
    )
    return IssuedBuyerSession(session=session, token=session_token)


def find_active_session(raw_token: str, moment: datetime | None = None) -> BuyerSession | None:
    """Sesión viva para el token de la cookie, o ``None``."""
    if not _TOKEN_FORMAT.fullmatch(raw_token):
        return None
    moment = moment or timezone.now()
    session = (
        BuyerSession.objects.select_related("client", "application")
        .filter(session_token_hash=hash_token(raw_token))
        .first()
    )
    if session is None or not session.is_active_at(moment):
        return None
    if not is_active_primary(session.application_id, session.client_id):
        return None
    return session


def touch_session(session: BuyerSession, moment: datetime | None = None) -> None:
    """Actualiza ``last_seen_at`` sin escribir en cada petición."""
    moment = moment or timezone.now()
    if session.last_seen_at is not None and moment - session.last_seen_at < LAST_SEEN_RESOLUTION:
        return
    BuyerSession.objects.filter(pk=session.pk).update(last_seen_at=moment)
    session.last_seen_at = moment


def logout_buyer_session(raw_token: str | None) -> None:
    """Revoca la sesión de la cookie. Sin cookie o con una sesión cerrada, no hace nada."""
    if not raw_token or not _TOKEN_FORMAT.fullmatch(raw_token):
        return
    session = BuyerSession.objects.filter(
        session_token_hash=hash_token(raw_token), revoked_at__isnull=True
    ).first()
    if session is None:
        return
    session.revoked_at = timezone.now()
    session.save(update_fields=["revoked_at"])
    logger.info("Sesión de comprador %s cerrada por el comprador", session.pk)
