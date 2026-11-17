"""Eventos de dominio de las tareas (paso 12).

El registro de actividad (parte 3) y las notificaciones (paso 13) se suscriben. Se
envían con ``transaction.on_commit``: solo si la escritura se confirmó.

- ``task_created``: ``task`` y ``actor``.
- ``task_completed``: ``task`` y ``actor``.
- ``task_cancelled``: ``task``, ``reason`` y ``actor``.
"""

from django.dispatch import Signal

task_created = Signal()
task_completed = Signal()
task_cancelled = Signal()
