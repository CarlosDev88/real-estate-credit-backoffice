"""Huella del expediente documental (decisión 23).

SHA-256 de la lista, ordenada por ``slot_id``, de los slots vigentes con ``(slot_id,
status, current_file_id, sha256 del archivo vigente, waiver_reason_item_id,
expires_at)``. Cambia con cualquier carga, decisión, exoneración o reapertura, y no
depende de la versión de la solicitud (acordada 6). La usan el paquete (Parte 7), la
radicación (paso 11) y los tests.
"""

import hashlib
import json
from typing import Any

from apps.applications.models import CreditApplication
from apps.documents.models import ApplicationDocumentSlot


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def dossier_fingerprint(application: CreditApplication) -> str:
    rows = (
        ApplicationDocumentSlot.objects.filter(application=application, retired_at__isnull=True)
        .order_by("pk")
        .values_list(
            "pk",
            "status",
            "current_file_id",
            "current_file__file_object__sha256",
            "waiver_reason_item_id",
            "current_file__expires_at",
        )
    )
    payload = [
        [str(slot_id), status, _text(file_id), sha256, _text(waiver_id), _text(expires_at)]
        for slot_id, status, file_id, sha256, waiver_id, expires_at in rows
    ]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
