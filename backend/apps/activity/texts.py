"""Títulos de la actividad que también usa el backfill (migración ``0003``). Solo
texto: sin consultas, para que la migración los use con sus modelos históricos."""

TITLE_MAX_LENGTH = 180


def application_created_title(code: str) -> str:
    return f"Solicitud {code} creada"


def status_changed_title(from_label: str, to_label: str) -> str:
    return f"Pasó de {from_label} a {to_label}"


def clip(text: str, length: int = TITLE_MAX_LENGTH) -> str:
    """Recorta un título largo (un nombre de documento o de tarea muy extenso)."""
    return text if len(text) <= length else text[: length - 1] + "…"
