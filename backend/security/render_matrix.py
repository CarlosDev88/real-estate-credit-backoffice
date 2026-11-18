"""Genera ``docs/seguridad/03-matriz-acceso.md`` desde ``tests/security/access_matrix.py``.

Uso, desde ``backend/``::

    python security/render_matrix.py          # escribe el documento
    python security/render_matrix.py --check  # sale con 1 si el documento no está al día

No necesita Django ni base de datos: la matriz es una tabla de Python. No editar el
documento a mano: se cambia ``access_matrix.py`` (o los textos de aquí) y se vuelve a
generar.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from tests.security import access_matrix as m  # noqa: E402

OUTPUT = BACKEND.parent / "docs" / "seguridad" / "03-matriz-acceso.md"

CELL = {
    m.ALLOW: "✓",
    m.DENY_401: "✗ 401",
    m.DENY_403: "✗ 403",
    m.HIDE_404: "✗ 404",
}
SHORT_ACTOR = {
    "anon": "sin sesión",
    "admin": "admin",
    "advisor_owner": "asesor dueño",
    "advisor_other": "otro asesor",
    "broker_owner": "broker dueño",
    "broker_other": "otro broker",
    "partner": "constructora",
    "buyer_owner": "comprador dueño",
    "buyer_other": "otro comprador",
}

INTRO = """# Auditoría de seguridad — Parte 3: matriz de acceso (BOLA / BFLA)

> Documento generado por `backend/security/render_matrix.py` desde
> `backend/tests/security/access_matrix.py`. No se edita a mano.

**Qué se probó:** que nadie vea ni toque lo que no le corresponde (OWASP API1:2023 *Broken
Object Level Authorization* y API5:2023 *Broken Function Level Authorization*). Cada una
de las {operations} operaciones del contrato se pide como cada uno de los 9 actores, sobre
los recursos del **lado A**, y se compara el estado con lo esperado: **{cases} casos**.

**Resultado:** {gap_summary} Además, en las respuestas permitidas al broker y al comprador
se comprueba que no lleguen campos prohibidos (montos detallados, archivos y URL firmadas,
notas y comentarios internos) y que el documento del cliente llegue enmascarado al broker.

**Cómo se repite:** `pytest tests/security` (en el CI corre con el resto de la suite).
Son 2150 pruebas (la matriz, su cobertura del contrato y los casos explícitos); en local
tardan ~75 s con la base de pruebas ya creada, de los que ~18 s son la construcción del
mundo.

## Los actores

| Actor | Quién es en el mundo de prueba |
| --- | --- |
| `anon` | Sin sesión. |
| `admin` | `admin@demo.local` (`ADMIN`). |
| `advisor_owner` | `asesora.lucia@demo.local`, asesora asignada a las solicitudes del lado A. |
| `advisor_other` | `asesor.andres@demo.local`, asesor del lado B. |
| `broker_owner` | `broker@demo.local`, originó las oportunidades del lado A. |
| `broker_other` | `broker.b@demo.local`, originó las del lado B. |
| `partner` | `constructora@demo.local` (`CONSTRUCTION_PARTNER`), de la constructora del lado A. |
| `buyer_owner` | Sesión del comprador de la solicitud A. |
| `buyer_other` | Sesión del comprador de la solicitud B. |

El mundo (`backend/tests/security/conftest.py`) tiene dos de cada cosa, una por lado, creada
con los servicios del dominio: clientes, oportunidades, solicitudes radicada, desembolsada,
lista para radicar y en borrador, participantes, perfiles e ingresos, inmueble y
financiación, slots con archivos, paquete, radicación, respuestas con evidencia,
notificaciones, tareas, notas, enlace y sesión del comprador con consentimientos,
liquidación de comisión con sus partes, exportación de reportes y dos constructoras con un
proyecto activo cada una.

## Cómo leer la tabla

- **✓** = permitido: 2xx, o un 4xx de negocio que muestra que pasó la autorización
  (400, 409, 412, 422, 428). En las escrituras basta con eso: el efecto lo prueban los
  módulos.
- **✗ 401** = sin sesión válida para esa ruta (las rutas internas leen la cookie interna y
  las del portal, la del comprador).
- **✗ 403** = con sesión, sin el permiso del rol.
- **✗ 404** = con permiso, pero el recurso está fuera de su alcance: no confirma que existe
  (API §3).
- **⚠ SEC-NN** = brecha conocida: la prueba está marcada `xfail(strict=True)`.

Fuentes de lo esperado, en este orden: REQ §3 (si choca con la API, manda REQ), API §3,
API §25 y la sección de cada módulo, y el `required_permissions` de cada vista con los
permisos sembrados por rol.
"""

PATTERNS_TITLE = """
## Patrones

Cada fila de la matriz usa uno de estos patrones (una letra por actor: `A` permitido,
`U` 401, `F` 403, `H` 404, en el orden de la tabla).

| Patrón | Letras | Operaciones | Razón |
| --- | --- | --- | --- |
"""

EXPLICIT_ROWS: list[tuple[str, str, str]] = [
    (
        (
            "Ids del lado B en el **cuerpo** (`opportunity_id`, `client_id` (asesor y "
            "broker), `application_id` y `opportunity_id` de tareas, `package_job_id`, "
            "`corrects_response_id`, `observations[].document_slot_id`, `document_file_id`)"
        ),
        (
            "Con el id propio la operación pasa; con el del lado B responde **igual que con "
            "un id que no existe** (mismo estado y código, el error nombra el campo) y "
            "nunca 2xx"
        ),
        ("✓ los 10"),
    ),
    (
        (
            "`participant_id`, `filing_id`, `slot_id`, `assigned_to`, `beneficiary_user_id` "
            "en el cuerpo"
        ),
        ("El contrato no tiene esos campos en ninguna escritura (una prueba lo vigila)"),
        ("no aplica"),
    ),
    (
        ("Tarea de una solicitud propia asignada a otro asesor"),
        (
            "Permitido por API §15 (`assigned_to_id` debe ser ADMIN o ADVISOR activo); "
            "queda fijado en una prueba"
        ),
        ("✓ documentado"),
    ),
    (
        (
            "Comprador A con ids del comprador B en `/buyer/applications/{id}`, "
            "`/buyer/document-files/{id}/download`, `/buyer/notifications/{id}/read`"
        ),
        ("404 y la notificación ajena sigue sin leer"),
        ("✓"),
    ),
    (
        (
            "Filtros con ids de otro alcance (`advisor_id`, `client_id`, `broker_id`, "
            "`application_id`, `opportunity_id`, `assigned_to_id`, `participant_id`, "
            "`partner_id`) en 16 listados"
        ),
        ("200 sin ningún id ni código del lado B (o 403)"),
        ("✓ los 16"),
    ),
    (
        (
            "Filtros de reportes y dashboard con `advisor_id` ajeno (7 rutas) y exportación "
            "con `advisor_id` ajeno"
        ),
        ("403, como pide API §22"),
        ("✓ los 8"),
    ),
    (
        ("Broker en `/applications/{id}` y `/applications/{id}/summary` de su solicitud"),
        ("Solo los campos del resumen (`BROKER_APPLICATION_SUMMARY_FIELDS`)"),
        ("✓"),
    ),
    (
        ("Constructora en todas las rutas de expedientes, clientes y oportunidades (lado A y B)"),
        ("403 o 404 en todas"),
        ("✓"),
    ),
    (
        ("Constructora sobre la otra constructora y su proyecto"),
        ("404"),
        ("✓"),
    ),
    (
        ("Usuario **desactivado** con la cookie de acceso vigente"),
        ("401 en la siguiente petición"),
        ("✓"),
    ),
    (
        ("Usuario al que **le quitaron el rol**, con la cookie vigente"),
        ("403 en la siguiente petición: los permisos se leen en cada petición"),
        ("✓"),
    ),
]

EXPLICIT_HEAD = """
## Casos explícitos (spec §3.4)

`backend/tests/security/test_explicit_cases.py`, aparte de la tabla:

| Caso | Qué se comprueba | Resultado |
| --- | --- | --- |
"""

DECISIONS_TITLE = """
## Casos decididos con la regla general

Donde la documentación no define el caso (o se contradice) se aplicó la regla general del
proyecto o lo ya decidido:

"""

GAPS_TITLE = """
## Brechas

"""


def _gap_summary() -> str:
    gaps = sum(len(actors) for actors in m.KNOWN_GAPS.values())
    if not gaps:
        return "**ninguna brecha.** Todas las operaciones responden lo esperado para los 9 actores."
    return f"**{gaps} casos con brecha conocida** (ver la sección Brechas)."


def render() -> str:
    operations = list(m.MATRIX)
    out = [
        INTRO.format(
            operations=len(operations),
            cases=len(operations) * len(m.ACTORS),
            gap_summary=_gap_summary(),
        )
    ]

    # Conteo por actor.
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    for operation in operations:
        for actor in m.ACTORS:
            totals[actor][m.expected(operation, actor)] += 1
    out.append("\n## Resumen por actor\n\n| Actor | ✓ | ✗ 401 | ✗ 403 | ✗ 404 |\n")
    out.append("| --- | --- | --- | --- | --- |\n")
    for actor in m.ACTORS:
        t = totals[actor]
        out.append(
            f"| `{actor}` | {t[m.ALLOW]} | {t[m.DENY_401]} | {t[m.DENY_403]} | {t[m.HIDE_404]} |\n"
        )

    out.append(PATTERNS_TITLE)
    usage = Counter(m.MATRIX.values())
    for pattern, (name, note) in m.PATTERN_NOTES.items():
        if usage[pattern]:
            out.append(f"| `{name}` | `{pattern}` | {usage[pattern]} | {note} |\n")

    out.append("\n## La matriz\n")
    header = " | ".join(SHORT_ACTOR[a] for a in m.ACTORS)
    separator = " | ".join("---" for _ in m.ACTORS)
    section = None
    for operation in operations:
        method, path = operation.split(" ", 1)
        module = path.split("/")[3]
        if module != section:
            section = module
            out.append(f"\n### `/{module}`\n\n| Operación | Patrón | {header} |\n")
            out.append(f"| --- | --- | {separator} |\n")
        name = m.PATTERN_NOTES.get(m.MATRIX[operation], ("—", ""))[0]
        cells = []
        for actor in m.ACTORS:
            gap = m.KNOWN_GAPS.get(operation, {}).get(actor)
            cells.append(f"⚠ {gap}" if gap else CELL[m.expected(operation, actor)])
        short = path.removeprefix("/api/v1")
        out.append(f"| `{method} {short}` | `{name}` | {' | '.join(cells)} |\n")

    out.append(EXPLICIT_HEAD)
    for row in EXPLICIT_ROWS:
        out.append("| " + " | ".join(row) + " |\n")
    out.append(DECISIONS_TITLE)
    for operation, reason in m.GENERAL_RULE_DECISIONS.items():
        out.append(f"- `{operation.removeprefix('/api/v1').replace('/api/v1', '')}`: {reason}\n")

    out.append(GAPS_TITLE)
    if not m.KNOWN_GAPS:
        out.append(
            "Ninguna. La matriz y los casos explícitos pasan sin `xfail`. Los hallazgos "
            "abiertos de las otras partes están en [`hallazgos.md`](hallazgos.md).\n"
        )
    else:
        for operation, actors in m.KNOWN_GAPS.items():
            for actor, gap in actors.items():
                out.append(f"- `{operation}` como `{actor}`: {gap}\n")
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="no escribe; falla si difiere")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} no está al día: python security/render_matrix.py")
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Escrito {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
