"""``record_audit``: la única forma de crear un evento de auditoría (API §24.1).

- **Éxito:** se escribe con ``transaction.on_commit``, para no auditar algo que se
  deshizo. Fuera de una transacción, se escribe en el acto.
- **Denegado o fallido:** se escribe de inmediato. Si se está dentro de una transacción
  propia del código (no la que abre una prueba), va por la conexión ``audit``: misma base,
  otra conexión en autocommit, así que el rollback de la operación no lo borra.
- **Contexto:** ``request_id`` sale de ``RequestIDMiddleware`` (o uno nuevo fuera de una
  petición, por ejemplo en un comando) y la IP de ``REMOTE_ADDR``
  (``apps.audit.context``).
- **Nunca rompe la operación:** cualquier error al auditar se registra en el log.
- ``metadata`` pasa siempre por ``sanitize_metadata``.
"""

import logging
import uuid
from typing import Any

from django.db import connections, models, transaction
from django.http import HttpRequest

from apps.audit.actions import AuditResult
from apps.audit.context import get_client_ip, request_ip
from apps.audit.models import AuditEvent
from apps.audit.sanitize import sanitize_metadata
from apps.identity.models import BuyerSession, User
from config.request_context import get_request_id

logger = logging.getLogger(__name__)

AUDIT_DATABASE = "audit"

# Un modelo, ``(resource_type, resource_id)`` o solo el ``resource_type``.
Resource = models.Model | tuple[str, Any] | str
Actor = User | BuyerSession | None


def resource_ref(resource: Resource) -> tuple[str, uuid.UUID | None, dict[str, Any]]:
    """Tipo e id del recurso. El tipo de un modelo es su tabla (``credit_applications``).
    Un id que no es UUID va en ``metadata.resource_pk``."""
    if isinstance(resource, models.Model):
        kind, raw_id = resource._meta.db_table, resource.pk
    elif isinstance(resource, tuple):
        kind, raw_id = resource
    else:
        kind, raw_id = resource, None
    if raw_id is None or isinstance(raw_id, uuid.UUID):
        return kind, raw_id, {}
    try:
        return kind, uuid.UUID(str(raw_id)), {}
    except ValueError:
        return kind, None, {"resource_pk": str(raw_id)}


def _actor_from(request: HttpRequest | None) -> Actor:
    if request is None:
        return None
    auth = getattr(request, "auth", None)
    if isinstance(auth, BuyerSession):
        return auth
    user = getattr(request, "user", None)
    return user if isinstance(user, User) else None


def in_code_transaction(alias: str = "default") -> bool:
    """Si hay una transacción abierta por el código. Las que abre ``TestCase`` (y
    pytest-django) no cuentan: así las pruebas se comportan como producción."""
    connection = connections[alias]
    return any(not getattr(block, "_from_testcase", False) for block in connection.atomic_blocks)


def _save(event: AuditEvent, alias: str) -> None:
    try:
        event.save(using=alias)
    except Exception:
        logger.exception("No se pudo registrar la auditoría %s (%s)", event.action, event.result)


def build_event(
    action: str,
    resource: Resource,
    result: str,
    *,
    actor: Actor = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    actor = actor or _actor_from(request)
    resource_type, resource_id, extra = resource_ref(resource)
    return AuditEvent(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        actor_user=actor if isinstance(actor, User) else None,
        actor_buyer_session=actor if isinstance(actor, BuyerSession) else None,
        request_id=get_request_id() or str(uuid.uuid4()),
        ip_address=request_ip(request) if request is not None else get_client_ip(),
        metadata=sanitize_metadata({**extra, **(metadata or {})}),
    )


def record_audit(
    action: str,
    resource: Resource,
    result: str = AuditResult.SUCCESS,
    *,
    actor: Actor = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> None:
    try:
        event = build_event(
            action, resource, result, actor=actor, metadata=metadata, request=request
        )
    except Exception:
        logger.exception("No se pudo preparar la auditoría %s", action)
        return
    if not in_code_transaction():
        _save(event, "default")
    elif result == AuditResult.SUCCESS:
        transaction.on_commit(lambda: _save(event, "default"))
    else:
        _save(event, AUDIT_DATABASE)
