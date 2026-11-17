"""``Idempotency-Key`` en los ``POST`` críticos (API §6).

Es opcional: sin la cabecera, la vista corre como siempre. Con la cabecera:

- La clave vale para su actor (usuario interno o sesión del comprador), el método y la
  ruta; la de otro actor es independiente. Dura ``KEY_LIFETIME`` (24 h).
- La primera petición reserva la clave en su propia transacción (``response_status``
  nulo) y corre la vista. Si responde ``2xx``, guarda la respuesta; si no, o si lanza un
  error, libera la clave para que se pueda reintentar.
- Misma clave y mismo cuerpo, ya terminada: la respuesta original, con su código y sus
  cabeceras (``ETag``).
- Misma clave y otro cuerpo: ``422 IDEMPOTENCY_CONFLICT``.
- Misma clave mientras la primera sigue en curso: ``409 IDEMPOTENCY_IN_PROGRESS``. No se
  espera el bloqueo: el cliente reintenta.
- Una operación cuya respuesta no se guarda (``store_response=False``: el enlace mágico,
  porque lleva el token en claro): ``409 IDEMPOTENCY_REPLAY_UNAVAILABLE``.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.idempotency.exceptions import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyReplayUnavailable,
)
from apps.idempotency.models import IdempotencyKey
from apps.identity.models import BuyerSession, User

HEADER = "Idempotency-Key"
KEY_LIFETIME = timedelta(hours=24)
# Caracteres visibles de ASCII, sin espacios, hasta la longitud de la columna.
KEY_FORMAT = re.compile(r"[\x21-\x7e]{1,100}")
# Cabeceras que la respuesta repetida conserva.
REPLAYED_HEADERS = ("ETag", "Location")

Actor = User | BuyerSession


@dataclass(frozen=True)
class Claim:
    record: IdempotencyKey
    # La respuesta original, si la clave ya terminó.
    replay: Response | None = None


def request_key(request: Request) -> str | None:
    """La clave de la cabecera, o ``None`` si no viene. Mal formada: ``400``."""
    raw = request.headers.get(HEADER)
    if raw is None:
        return None
    if not KEY_FORMAT.fullmatch(raw):
        raise ValidationError(
            {HEADER: ["Debe tener de 1 a 100 caracteres visibles, sin espacios."]}
        )
    return raw


def request_actor(request: Request) -> Actor | None:
    if isinstance(request.auth, BuyerSession):
        return request.auth
    user = request.user
    return user if isinstance(user, User) and user.is_authenticated else None


def request_hash(request: Request) -> str:
    """Huella del cuerpo: el JSON con las claves ordenadas, sin depender de espacios ni
    del orden en que llegaron."""
    canonical = json.dumps(request.data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _actor_fields(actor: Actor) -> dict[str, Any]:
    if isinstance(actor, BuyerSession):
        return {"user": None, "buyer_session": actor}
    return {"user": actor, "buyer_session": None}


def _route(request: Request) -> dict[str, str]:
    return {"method": str(request.method), "route_fingerprint": request.path[:180]}


def _keys_of(actor: Actor, key: str, request: Request) -> QuerySet[IdempotencyKey]:
    return IdempotencyKey.objects.filter(**_actor_fields(actor), key=key, **_route(request))


def claim(actor: Actor, key: str, request: Request) -> Claim:
    """Reserva la clave o devuelve la respuesta original. Ver el docstring del módulo."""
    fingerprint = request_hash(request)
    now = timezone.now()
    with transaction.atomic():
        existing = _keys_of(actor, key, request).select_for_update().first()
        if existing is not None and existing.expires_at <= now:
            existing.delete()
            existing = None
        if existing is None:
            try:
                with transaction.atomic():
                    record = IdempotencyKey.objects.create(
                        **_actor_fields(actor),
                        key=key,
                        **_route(request),
                        request_hash=fingerprint,
                        expires_at=now + KEY_LIFETIME,
                    )
            except IntegrityError as exc:
                # Otra petición con la misma clave la reservó en este instante.
                raise IdempotencyInProgress() from exc
            return Claim(record)
    if existing.request_hash != fingerprint:
        raise IdempotencyConflict()
    if existing.response_status is None:
        raise IdempotencyInProgress()
    if existing.response_body is None:
        raise IdempotencyReplayUnavailable()
    replay = Response(
        existing.response_body,
        status=existing.response_status,
        headers=existing.response_headers,
    )
    return Claim(existing, replay)


def _resource_id(data: Any) -> uuid.UUID | None:
    if not isinstance(data, dict):
        return None
    try:
        return uuid.UUID(str(data.get("id")))
    except ValueError:
        return None


def complete(record: IdempotencyKey, response: Response, *, store_response: bool) -> None:
    """Guarda la respuesta ``2xx``. Sin ``store_response``, solo el código y el id."""
    record.response_status = response.status_code
    record.resource_id = _resource_id(response.data)
    if store_response:
        # El mismo JSON que recibe el cliente, ya serializado.
        record.response_body = json.loads(JSONRenderer().render(response.data) or b"null")
        record.response_headers = {
            name: response[name] for name in REPLAYED_HEADERS if response.has_header(name)
        }
    record.save(
        update_fields=["response_status", "response_body", "response_headers", "resource_id"]
    )


def release(record: IdempotencyKey) -> None:
    """La operación no terminó en ``2xx``: la clave queda libre para reintentar."""
    IdempotencyKey.objects.filter(pk=record.pk).delete()


def purge_expired() -> int:
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lte=timezone.now()).delete()
    return deleted
