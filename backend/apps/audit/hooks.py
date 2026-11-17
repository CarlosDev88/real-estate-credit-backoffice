"""Auditoría de las respuestas de la API (lo que no tiene señal).

``AuditContextMiddleware`` llama a ``audit_response`` con cada respuesta. Solo mira las
respuestas de DRF (las que traen ``renderer_context``):

- **``403``:** ``ACCESS_DENIED`` (``DENIED``), con la ruta, el método y el código del error.
- **``429``:** ``AUTH_RATE_LIMITED`` (``DENIED``).
- **Otro 4xx de una vista con ``audit_failure_action``:** esa acción, ``FAILED``, con el
  código del error (el login, la renovación de sesión y el consumo del enlace).
- **2xx de una vista con ``audit_actions``** (``{método: acción}``): esa acción,
  ``SUCCESS``. El recurso es ``audit_resource_type`` con el ``id`` de la respuesta o, si no
  trae, el primer argumento de la ruta. Solo se guardan los **nombres** de los campos
  enviados, nunca los valores ni la respuesta (que puede traer una URL firmada).

Nunca se guarda el cuerpo. Un correo enviado (``email``) va enmascarado.
"""

import logging
from collections.abc import Mapping
from typing import Any

from django.http import HttpResponse

from apps.audit.actions import AuditAction, AuditResult
from apps.audit.sanitize import mask_email
from apps.audit.services import record_audit

logger = logging.getLogger(__name__)

DEFAULT_RESOURCE_TYPE = "api"


def _data(request: Any) -> Mapping[str, Any]:
    try:
        data = request.data
    except Exception:
        return {}
    return data if isinstance(data, Mapping) else {}


def _base_metadata(request: Any, view: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "method": request.method,
        "path": request.path,
        "view": type(view).__name__,
    }
    metadata.update({key: str(value) for key, value in getattr(view, "kwargs", {}).items()})
    email = _data(request).get("email")
    if email:
        metadata["email"] = mask_email(str(email))
    return metadata


def _resource(view: Any, response: HttpResponse) -> tuple[str, Any]:
    resource_type = getattr(view, "audit_resource_type", DEFAULT_RESOURCE_TYPE)
    data = getattr(response, "data", None)
    if isinstance(data, Mapping) and data.get("id"):
        return resource_type, data["id"]
    kwargs = getattr(view, "kwargs", {}) or {}
    return resource_type, next(iter(kwargs.values()), None)


def _error_code(response: HttpResponse) -> str | None:
    data = getattr(response, "data", None)
    return data.get("code") if isinstance(data, Mapping) else None


def audit_response(response: HttpResponse) -> None:
    context = getattr(response, "renderer_context", None) or {}
    view, request = context.get("view"), context.get("request")
    if view is None or request is None:
        return
    status_code = response.status_code
    if status_code in (403, 429):
        action = AuditAction.ACCESS_DENIED if status_code == 403 else AuditAction.AUTH_RATE_LIMITED
        result = AuditResult.DENIED
    elif 400 <= status_code < 500 and getattr(view, "audit_failure_action", None):
        action, result = view.audit_failure_action, AuditResult.FAILED
    elif 200 <= status_code < 300 and request.method in getattr(view, "audit_actions", {}):
        action, result = view.audit_actions[request.method], AuditResult.SUCCESS
    else:
        return
    metadata = _base_metadata(request, view)
    if result == AuditResult.SUCCESS:
        metadata["fields"] = sorted(str(key) for key in _data(request))
    else:
        metadata.update({"status": status_code, "code": _error_code(response)})
    record_audit(action, _resource(view, response), result, request=request, metadata=metadata)


def safe_audit_response(response: HttpResponse) -> None:
    try:
        audit_response(response)
    except Exception:
        logger.exception("No se pudo auditar la respuesta")
