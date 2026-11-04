"""Autorización por código de permiso (``permissions.code``).

Uso en una vista::

    class CatalogListView(APIView):
        permission_classes = [HasPermissionCode]
        required_permissions = {"GET": "catalogs.read", "POST": "catalogs.create"}

Un método implementado que no aparece en ``required_permissions`` se niega (deny by
default). ``HEAD`` y ``OPTIONS`` usan el permiso de ``GET``.
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.identity.models import User
from apps.identity.services import get_access_profile

_PERMISSIONS_CACHE_ATTR = "_permission_codes"
_READ_ALIASES = {"HEAD": "GET", "OPTIONS": "GET"}


def get_request_permission_codes(request: Request) -> frozenset[str]:
    """Permisos del usuario autenticado, calculados una sola vez por petición."""
    cached = getattr(request, _PERMISSIONS_CACHE_ATTR, None)
    if cached is not None:
        return cached

    user = request.user
    codes: frozenset[str] = frozenset()
    if isinstance(user, User) and user.is_authenticated:
        codes = frozenset(get_access_profile(user).permissions)
    setattr(request, _PERMISSIONS_CACHE_ATTR, codes)
    return codes


class HasPermissionCode(BasePermission):
    message = "No tienes permiso para realizar esta acción."

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        method = (request.method or "").upper()
        if not hasattr(view, method.lower()):
            return True  # DRF responderá 405 METHOD_NOT_ALLOWED.
        required: dict[str, str] = getattr(view, "required_permissions", {})
        code = required.get(_READ_ALIASES.get(method, method))
        if code is None:
            return False
        return code in get_request_permission_codes(request)
