"""Eventos de dominio del módulo crm.

Los módulos de actividad (paso 12) y auditoría (paso 14) se suscribirán para dejar
la bitácora que exige RF-11 ("la reasignación queda registrada en la bitácora").

- ``opportunity_assigned``: ``opportunity``, ``previous_advisor_id`` (UUID o ``None``
  en la primera asignación), ``advisor_id`` (UUID), ``actor`` y ``reason``.
- ``opportunity_status_changed``: ``opportunity``, ``from_status``, ``to_status``,
  ``transition_code``, ``actor`` y ``comment``.
"""

from django.dispatch import Signal

opportunity_assigned = Signal()
opportunity_status_changed = Signal()
