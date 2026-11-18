"""Límite de consumo de los endpoints costosos del dashboard y los reportes
(REQUERIMIENTOS §9.3): ``AUTH_RATE_LIMITS["reports"]``, por usuario. Todos los
endpoints de ``/dashboard/*`` y ``/reports/*`` comparten el mismo cupo."""

from typing import Any

from rest_framework.request import Request

from apps.identity.throttling import AuthRateThrottle


class ReportsRateThrottle(AuthRateThrottle):
    scope = "reports"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        user_id = getattr(request.user, "pk", None)
        if user_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self._hashed(f"user|{user_id}")}
