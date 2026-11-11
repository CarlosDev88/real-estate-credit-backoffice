"""Eventos de dominio del módulo partners.

Los módulos de actividad (paso 12) y auditoría (paso 14) se suscribirán a estas
señales para registrar quién hizo el cambio y por qué. Mientras tanto, el motivo
se escribe en el log de la aplicación.

Argumentos de ``project_status_changed``: ``project``, ``from_status``,
``to_status``, ``transition_code``, ``actor`` y ``reason``.

Argumentos de ``partner_status_changed``: ``partner``, ``from_status``,
``to_status``, ``actor`` y ``reason``.
"""

from django.dispatch import Signal

project_status_changed = Signal()
partner_status_changed = Signal()
