"""Reporte del CI del backend para el resumen del run y el comentario del PR.

Lee las salidas que dejan los pasos del workflow en ``CI_REPORT_DIR`` (por defecto
``.ci-report``) y el resultado de cada paso (variables ``OUTCOME_*``, con los valores de
``steps.<id>.outcome``). Escribe un Markdown en ``report.md`` y en ``$GITHUB_STEP_SUMMARY``.

Solo usa la librería estándar y nunca hace fallar el job: si un paso no corrió, su fila sale
como ⏭️; si un archivo no se puede leer, la fila lo dice; si algo inesperado falla, escribe
un reporte mínimo y termina con código 0.

También define ``WarningRecorder``, con el que ``tests/conftest.py`` guarda los warnings de
pytest en ``warnings.json``.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import traceback
import warnings
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePath
from typing import Any

MARKER = "<!-- ci-report:backend -->"
TITLE = "Backend CI"
REPORT_FILE = "report.md"
WARNINGS_FILE = "warnings.json"
DEFAULT_REPORT_DIR = ".ci-report"
DEFAULT_COVERAGE_MIN = 95.0

# GitHub admite 65 536 caracteres por comentario; se deja margen.
MAX_REPORT_CHARS = 60_000
# Líneas por bloque <details>; si el reporte no cabe, se reintenta con menos.
DETAIL_LINE_LIMITS = (50, 20, 5)
MAX_LINE_CHARS = 200
MAX_SUMMARY_CHARS = 160
MAX_TITLE_CHARS = 120
MAX_FAILED_TESTS = 20
LOWEST_COVERAGE_MODULES = 5
TAIL_LINES = 30
DETAILS_OMITTED = "_El detalle no cabe en el comentario: está en el log del run y en el artefacto._"

# Valores de steps.<id>.outcome que significan que el paso corrió.
SUCCESS = "success"
FAILURE = "failure"
CANCELLED = "cancelled"
RAN = frozenset({SUCCESS, FAILURE})

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]|~#!])")
BACKTICK_RUN = re.compile(r"`+")
COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")
DIGITS = re.compile(r"[0-9]+")
SERVER_URL = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

MYPY_ERROR = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?:\d+:)? error: (?P<message>.*?)(?:  \[(?P<code>[\w-]+)\])?$"
)
MIGRATIONS_FOR = re.compile(r"^Migrations for '([^']+)':", re.MULTILINE)
SPECTACULAR_ISSUE = re.compile(
    r"^(?:(?P<location>.+?): )?(?P<severity>Warning|Error)(?: \[[^\]]*\])?: (?P<message>.+)$"
)
SPECTACULAR_TOTALS = re.compile(r"^(Warnings|Errors):\s+(\d+)", re.MULTILINE)
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

# Nombres de las filas, en el orden de la tabla.
RUFF_LINT = "Ruff (lint)"
RUFF_FORMAT = "Ruff (formato)"
MYPY = "Mypy"
MIGRATIONS = "Migraciones"
TESTS = "Tests"
COVERAGE = "Cobertura"
WARNINGS = "Advertencias"
OPENAPI = "Contrato OpenAPI"


class Status(Enum):
    PASSED = "✅"
    WARNING = "⚠️"
    FAILED = "❌"
    SKIPPED = "⏭️"


@dataclass(frozen=True)
class Detail:
    """Bloque ``<details>``: cada entrada son una o más líneas de salida de una herramienta."""

    title: str
    entries: Sequence[str]
    # Entradas descartadas antes de llegar aquí (por ejemplo, tests más allá de los 20).
    hidden: int = 0


@dataclass(frozen=True)
class Verdict:
    status: Status
    summary: str
    details: tuple[Detail, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    summary: str
    blocking: bool
    details: tuple[Detail, ...] = ()


@dataclass(frozen=True)
class Context:
    report_dir: Path
    outcomes: Mapping[str, str]
    coverage_min: float
    base_dir: Path

    def outcome(self, key: str) -> str:
        return self.outcomes.get(key, "")

    def read_text(self, name: str) -> str | None:
        path = self.report_dir / name
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def relative(self, filename: str) -> str:
        """Ruta legible: relativa a ``backend/`` o, si es de una librería, desde site-packages."""
        path = PurePath(filename)
        if path.is_absolute():
            try:
                return path.relative_to(self.base_dir).as_posix()
            except ValueError:
                pass
            if "site-packages" in path.parts:
                index = path.parts.index("site-packages")
                return PurePath(*path.parts[index + 1 :]).as_posix()
        return path.as_posix()


# --- Formato -------------------------------------------------------------------------------


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def format_percent(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " %"


def format_minimum(value: float) -> str:
    return f"{value:g}".replace(".", ",") + " %"


def format_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clean_line(text: str) -> str:
    """Una línea de salida, sin colores ni caracteres de control, y truncada."""
    text = ANSI_ESCAPE.sub("", text).replace("\t", "    ")
    return truncate(CONTROL_CHARS.sub("", text).rstrip(), MAX_LINE_CHARS)


def md_inline(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Texto seguro para una celda de tabla: sin HTML, sin Markdown y sin saltos de línea."""
    text = " ".join(clean_line(line).strip() for line in text.splitlines())
    text = html.escape(truncate(text, limit), quote=False)
    return MARKDOWN_SPECIAL.sub(r"\\\1", text)


def html_text(text: str) -> str:
    """Texto seguro dentro de una etiqueta HTML (``<summary>``)."""
    return html.escape(truncate(clean_line(text), MAX_TITLE_CHARS), quote=False)


def code_block(lines: Sequence[str]) -> str:
    """Bloque de código con una cerca más larga que cualquier serie de comillas del texto."""
    longest = max((len(run) for line in lines for run in BACKTICK_RUN.findall(line)), default=0)
    fence = "`" * max(3, longest + 1)
    return "\n".join([fence, *lines, fence])


def tail(text: str | None, count: int = TAIL_LINES) -> list[str]:
    if not text:
        return []
    lines = [clean_line(line) for line in text.splitlines()]
    return [line for line in lines if line.strip()][-count:]


def first_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return clean_line(line.strip())
    return ""


def _to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return 0


def _ranked(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def _count_list(counter: Counter[str], limit: int = 5) -> str:
    ranked = _ranked(counter)
    text = ", ".join(f"{key}: {count}" for key, count in ranked[:limit])
    return text + (", …" if len(ranked) > limit else "")


def _tail_details(title: str, text: str | None) -> tuple[Detail, ...]:
    lines = tail(text)
    return (Detail(title, lines),) if lines else ()


# --- Ruff ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    column: int
    code: str
    message: str


def load_ruff(ctx: Context, name: str) -> list[Diagnostic] | None:
    text = ctx.read_text(name)
    if text is None:
        return None
    data = json.loads(text) if text.strip() else []
    if not isinstance(data, list):
        raise ValueError(f"{name}: se esperaba una lista")
    diagnostics = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_location = item.get("location")
        location: dict[str, Any] = raw_location if isinstance(raw_location, dict) else {}
        diagnostics.append(
            Diagnostic(
                path=ctx.relative(str(item.get("filename") or "?")),
                line=_to_int(location.get("row")),
                column=_to_int(location.get("column")),
                code=str(item.get("code") or "syntax-error"),
                message=str(item.get("message") or ""),
            )
        )
    return diagnostics


def check_ruff_lint(ctx: Context) -> Verdict:
    if ctx.outcome("ruff_lint") == SUCCESS:
        return Verdict(Status.PASSED, "Sin errores")
    diagnostics = load_ruff(ctx, "ruff.json")
    if not diagnostics:
        return Verdict(Status.FAILED, "Falló sin errores reportados (ver el log)")
    by_code = Counter(diagnostic.code for diagnostic in diagnostics)
    files = {diagnostic.path for diagnostic in diagnostics}
    ordered = sorted(
        diagnostics, key=lambda d: (-by_code[d.code], d.code, d.path, d.line, d.column)
    )
    errors = plural(len(diagnostics), "error", "errores")
    detail = Detail(
        f"{RUFF_LINT}: {errors} ({_count_list(by_code)})",
        [f"{d.code}  {d.path}:{d.line}:{d.column}  {d.message}" for d in ordered],
    )
    summary = f"{errors} en {plural(len(files), 'archivo', 'archivos')}"
    return Verdict(Status.FAILED, summary, (detail,))


def check_ruff_format(ctx: Context) -> Verdict:
    if ctx.outcome("ruff_format") == SUCCESS:
        return Verdict(Status.PASSED, "Sin cambios pendientes")
    diagnostics = load_ruff(ctx, "ruff-format.json")
    if not diagnostics:
        return Verdict(Status.FAILED, "Falló sin archivos reportados (ver el log)")
    files = sorted({d.path for d in diagnostics if d.code == "unformatted"})
    others = [d for d in diagnostics if d.code != "unformatted"]
    parts = []
    if files:
        parts.append(plural(len(files), "archivo sin formatear", "archivos sin formatear"))
    if others:
        parts.append(plural(len(others), "error", "errores"))
    summary = " · ".join(parts)
    entries = files + [f"{d.code}  {d.path}:{d.line}:{d.column}  {d.message}" for d in others]
    return Verdict(Status.FAILED, summary, (Detail(f"{RUFF_FORMAT}: {summary}", entries),))


# --- Mypy y migraciones --------------------------------------------------------------------


def check_mypy(ctx: Context) -> Verdict:
    if ctx.outcome("mypy") == SUCCESS:
        return Verdict(Status.PASSED, "Sin errores")
    text = ctx.read_text("mypy.txt")
    entries = []
    files = set()
    for line in (text or "").splitlines():
        match = MYPY_ERROR.match(clean_line(line))
        if match is None:
            continue
        path = ctx.relative(match["path"])
        files.add(path)
        code = f"[{match['code']}] " if match["code"] else ""
        entries.append(f"{path}:{match['line']}  {code}{match['message']}")
    if not entries:
        details = _tail_details(f"{MYPY}: salida", text)
        return Verdict(Status.FAILED, "Falló (ver el log)", details)
    errors = plural(len(entries), "error", "errores")
    summary = f"{errors} en {plural(len(files), 'archivo', 'archivos')}"
    return Verdict(Status.FAILED, summary, (Detail(f"{MYPY}: {errors}", entries),))


def check_migrations(ctx: Context) -> Verdict:
    if ctx.outcome("migrations") == SUCCESS:
        return Verdict(Status.PASSED, "Al día")
    text = ctx.read_text("migrations.txt")
    apps = MIGRATIONS_FOR.findall(text or "")
    if not apps:
        details = _tail_details(f"{MIGRATIONS}: salida", text)
        return Verdict(Status.FAILED, "Falló (ver el log)", details)
    summary = f"Faltan migraciones en: {', '.join(apps)}"
    lines = [clean_line(line) for line in (text or "").splitlines() if line.strip()]
    return Verdict(Status.FAILED, summary, (Detail(f"{MIGRATIONS}: {summary}", lines),))


# --- Tests y cobertura ---------------------------------------------------------------------


@dataclass(frozen=True)
class JUnitRun:
    passed: int
    failing: int
    skipped: int
    duration: float
    failures: tuple[tuple[str, str], ...]

    @property
    def total(self) -> int:
        return self.passed + self.failing + self.skipped


def load_junit(ctx: Context) -> JUnitRun | None:
    text = ctx.read_text("pytest.xml")
    if text is None:
        return None
    root = ET.fromstring(text)
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    passed = skipped = 0
    failures: list[tuple[str, str]] = []
    case_time = 0.0
    for case in root.iter("testcase"):
        case_time += float(case.get("time") or 0)
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is not None:
            classname, name = case.get("classname") or "", case.get("name") or "?"
            test_id = f"{classname}::{name}" if classname else name
            failures.append((test_id, first_line(problem.get("message") or problem.text)))
        elif case.find("skipped") is not None:
            skipped += 1
        else:
            passed += 1
    suite_time = sum(float(suite.get("time") or 0) for suite in suites)
    return JUnitRun(passed, len(failures), skipped, suite_time or case_time, tuple(failures))


def check_tests(ctx: Context) -> Verdict:
    succeeded = ctx.outcome("tests") == SUCCESS
    status = Status.PASSED if succeeded else Status.FAILED
    run = load_junit(ctx)
    if run is None:
        summary = (
            "Pasaron (sin resultados JUnit)" if succeeded else "Falló sin resultados (ver el log)"
        )
        return Verdict(status, summary)
    summary = (
        " · ".join(
            [
                plural(run.passed, "pasa", "pasan"),
                plural(run.failing, "falla", "fallan"),
                plural(run.skipped, "saltado", "saltados"),
            ]
        )
        + f" ({run.total} en {format_duration(run.duration)})"
    )
    if not run.failures:
        return Verdict(status, summary)
    shown = run.failures[:MAX_FAILED_TESTS]
    entries = [f"{name}\n    {message}" if message else name for name, message in shown]
    detail = Detail(
        f"Tests que fallan ({run.failing})", entries, hidden=len(run.failures) - len(shown)
    )
    return Verdict(status, summary, (detail,))


@dataclass(frozen=True)
class CoverageModule:
    path: str
    percent: float
    statements: int


def _resolve_source(filename: str, sources: Sequence[Path]) -> str:
    """En coverage.xml cada archivo es relativo a su fuente (``--cov``): se busca cuál es."""
    for source in sources:
        candidate = source / filename
        if candidate.is_file():
            return str(candidate)
    return str(sources[0] / filename) if len(sources) == 1 else filename


def load_coverage(ctx: Context) -> tuple[float, list[CoverageModule]] | None:
    text = ctx.read_text("coverage.xml")
    if text is None:
        return None
    root = ET.fromstring(text)
    valid = _to_int(root.get("lines-valid"))
    covered = _to_int(root.get("lines-covered"))
    total = 100.0 * covered / valid if valid else 100.0
    sources = [Path(s.text.strip()) for s in root.iter("source") if s.text and s.text.strip()]
    modules = []
    for item in root.iter("class"):
        lines = item.findall("lines/line")
        if not lines:
            continue
        hits = sum(1 for line in lines if _to_int(line.get("hits")) > 0)
        path = ctx.relative(_resolve_source(item.get("filename") or "?", sources))
        modules.append(CoverageModule(path, 100.0 * hits / len(lines), len(lines)))
    return total, modules


def check_coverage(ctx: Context) -> Verdict:
    succeeded = ctx.outcome("coverage") == SUCCESS
    status = Status.PASSED if succeeded else Status.FAILED
    suffix = " (con tests fallidos)" if ctx.outcome("tests") == FAILURE else ""
    minimum = format_minimum(ctx.coverage_min)
    data = load_coverage(ctx)
    if data is None:
        summary = (
            f"Sobre el mínimo ({minimum})"
            if succeeded
            else f"Por debajo del mínimo ({minimum}) o sin datos (ver el log)"
        )
        return Verdict(status, summary + suffix)
    total, modules = data
    summary = f"{format_percent(total)} (mínimo {minimum}){suffix}"
    if succeeded:
        return Verdict(status, summary)
    candidates = [module for module in modules if "migrations" not in PurePath(module.path).parts]
    lowest = sorted(candidates, key=lambda m: (m.percent, -m.statements, m.path))
    lowest = lowest[:LOWEST_COVERAGE_MODULES]
    entries = [
        f"{format_percent(m.percent):>8}  {m.path} "
        f"({plural(m.statements, 'sentencia', 'sentencias')})"
        for m in lowest
    ]
    title = f"{COVERAGE}: {plural(len(lowest), 'módulo', 'módulos')} con menos cobertura"
    return Verdict(status, summary, (Detail(title, entries),) if entries else ())


def coverage_skipped_summary(ctx: Context) -> str:
    return "Sin datos de cobertura" if ctx.outcome("tests") in RAN else "No corrió"


# --- Warnings de pytest --------------------------------------------------------------------


class WarningRecorder:
    """Acumula en memoria los warnings de pytest y los escribe una sola vez, al final.

    Lo usan los hooks de ``tests/conftest.py``; solo existe si ``CI_REPORT_DIR`` está definida.
    """

    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir
        self._records: list[dict[str, str | int]] = []

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> WarningRecorder | None:
        env = os.environ if environ is None else environ
        report_dir = env.get("CI_REPORT_DIR")
        return cls(Path(report_dir)) if report_dir else None

    def record(self, warning: warnings.WarningMessage, *, nodeid: str, when: str) -> None:
        self._records.append(
            {
                "category": warning.category.__name__,
                "message": str(warning.message),
                "filename": str(warning.filename),
                "lineno": warning.lineno,
                "nodeid": nodeid,
                "when": when,
            }
        )

    def write(self) -> Path | None:
        path = self.report_dir / WARNINGS_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._records, ensure_ascii=False, indent=2)
            path.write_text(content + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ci_report: no se pudo escribir {path}: {exc}", file=sys.stderr)
            return None
        return path


def load_warnings(ctx: Context) -> list[dict[str, Any]]:
    text = ctx.read_text(WARNINGS_FILE)
    if text is None:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{WARNINGS_FILE}: se esperaba una lista")
    return [item for item in data if isinstance(item, dict)]


def check_warnings(ctx: Context) -> Verdict:
    records = load_warnings(ctx)
    if not records:
        return Verdict(Status.PASSED, "Sin advertencias")
    by_category = Counter(str(record.get("category") or "Warning") for record in records)
    entries = []
    for category, count in _ranked(by_category):
        examples = Counter(
            (
                first_line(str(record.get("message") or "")),
                ctx.relative(str(record.get("filename") or "?")),
                _to_int(record.get("lineno")),
            )
            for record in records
            if str(record.get("category") or "Warning") == category
        )
        (message, filename, lineno), times = examples.most_common(1)[0]
        entries.append(
            f"{category} ({count}) · más frecuente, {plural(times, 'vez', 'veces')}:\n"
            f"    {filename}:{lineno}: {message}"
        )
    summary = f"{len(records)} ({_count_list(by_category)})"
    return Verdict(Status.WARNING, summary, (Detail(f"{WARNINGS} ({len(records)})", entries),))


# --- Contrato OpenAPI ----------------------------------------------------------------------


def _load_json(ctx: Context, name: str) -> Any | None:
    text = ctx.read_text(name)
    return json.loads(text) if text is not None else None


def _section(schema: Any, *keys: str) -> dict[str, Any]:
    for key in keys:
        schema = schema.get(key) if isinstance(schema, dict) else None
    return schema if isinstance(schema, dict) else {}


def _operations(schema: Any) -> dict[tuple[str, str], str]:
    operations = {}
    for path, item in _section(schema, "paths").items():
        if isinstance(item, dict):
            for method in HTTP_METHODS:
                if method in item:
                    operations[(path, method)] = json.dumps(item[method], sort_keys=True)
    return operations


def _schemas(schema: Any) -> dict[str, str]:
    return {
        name: json.dumps(value, sort_keys=True)
        for name, value in _section(schema, "components", "schemas").items()
    }


def _diff_keys(old: Mapping[Any, str], new: Mapping[Any, str]) -> list[tuple[str, Any]]:
    changes = [("+", key) for key in new.keys() - old.keys()]
    changes += [("-", key) for key in old.keys() - new.keys()]
    changes += [("~", key) for key in old.keys() & new.keys() if old[key] != new[key]]
    return changes


def contract_changes(committed: Any, generated: Any) -> tuple[list[str], list[str]]:
    """Rutas (método y path) y esquemas de ``components`` que cambiaron."""
    routes = sorted(
        _diff_keys(_operations(committed), _operations(generated)),
        key=lambda change: (change[1][0], HTTP_METHODS.index(change[1][1]), change[0]),
    )
    schemas = sorted(
        _diff_keys(_schemas(committed), _schemas(generated)),
        key=lambda change: (change[1], change[0]),
    )
    return (
        [f"{sign} {method.upper()} {path}" for sign, (path, method) in routes],
        [f"{sign} esquema {name}" for sign, name in schemas],
    )


def check_openapi(ctx: Context) -> Verdict:
    if ctx.outcome("openapi") == SUCCESS:
        return Verdict(Status.PASSED, "Al día")
    text = ANSI_ESCAPE.sub("", ctx.read_text("spectacular.txt") or "")
    issues = []
    severities: Counter[str] = Counter()
    for line in text.splitlines():
        match = SPECTACULAR_ISSUE.match(line)
        if match is not None:
            issues.append(clean_line(line))
            severities[match["severity"]] += 1
    # El resumen de spectacular cuenta las repeticiones; si no está, se cuentan las líneas.
    totals = {kind: int(count) for kind, count in SPECTACULAR_TOTALS.findall(text)}
    warnings_count = totals.get("Warnings", severities["Warning"])
    errors_count = totals.get("Errors", severities["Error"])
    if issues or warnings_count or errors_count:
        parts = []
        if errors_count:
            parts.append(plural(errors_count, "error del esquema", "errores del esquema"))
        if warnings_count:
            parts.append(
                plural(warnings_count, "advertencia del esquema", "advertencias del esquema")
            )
        summary = " y ".join(parts) or "Avisos del esquema"
        entries = issues or tail(text)
        return Verdict(
            Status.FAILED, summary, (Detail(f"{OPENAPI}: avisos de spectacular", entries),)
        )
    committed = _load_json(ctx, "openapi.committed.json")
    generated = _load_json(ctx, "openapi.generated.json")
    if committed is not None and generated is not None and committed != generated:
        routes, schemas = contract_changes(committed, generated)
        parts = []
        if routes:
            parts.append(plural(len(routes), "ruta", "rutas"))
        if schemas:
            parts.append(plural(len(schemas), "esquema", "esquemas"))
        verb = "cambió" if len(routes) + len(schemas) == 1 else "cambiaron"
        summary = f"Desactualizado: {verb} {' y '.join(parts)}" if parts else "Desactualizado"
        entries = routes + schemas or ["Cambios fuera de paths y components.schemas"]
        entries += tail(ctx.read_text("openapi-diff.txt"))
        title = f"{OPENAPI}: cambios sin regenerar"
        return Verdict(Status.FAILED, summary, (Detail(title, entries),))
    details = _tail_details(f"{OPENAPI}: salida de spectacular", text)
    return Verdict(Status.FAILED, "Falló la generación del contrato (ver el log)", details)


# --- Armado del reporte --------------------------------------------------------------------


def _not_run(ctx: Context) -> str:
    return "No corrió"


@dataclass(frozen=True)
class CheckSpec:
    name: str
    outcome_key: str
    build: Callable[[Context], Verdict]
    blocking: bool = True
    skipped_summary: Callable[[Context], str] = _not_run


CHECKS = (
    CheckSpec(RUFF_LINT, "ruff_lint", check_ruff_lint),
    CheckSpec(RUFF_FORMAT, "ruff_format", check_ruff_format),
    CheckSpec(MYPY, "mypy", check_mypy),
    CheckSpec(MIGRATIONS, "migrations", check_migrations),
    CheckSpec(TESTS, "tests", check_tests),
    CheckSpec(COVERAGE, "coverage", check_coverage, skipped_summary=coverage_skipped_summary),
    # Las advertencias salen de la corrida de tests y nunca bloquean.
    CheckSpec(WARNINGS, "tests", check_warnings, blocking=False),
    CheckSpec(OPENAPI, "openapi", check_openapi),
)
OUTCOME_KEYS = ("install", *dict.fromkeys(spec.outcome_key for spec in CHECKS))


def run_check(spec: CheckSpec, ctx: Context) -> CheckResult:
    outcome = ctx.outcome(spec.outcome_key)
    if outcome not in RAN:
        summary = "Cancelado" if outcome == CANCELLED else spec.skipped_summary(ctx)
        return CheckResult(spec.name, Status.SKIPPED, summary, spec.blocking)
    try:
        verdict = spec.build(ctx)
    except Exception:  # El reporte nunca falla por una salida inesperada.
        traceback.print_exc(file=sys.stderr)
        if not spec.blocking:
            status = Status.WARNING
        else:
            status = Status.FAILED if outcome == FAILURE else Status.PASSED
        verdict = Verdict(status, "No se pudo leer el detalle (ver el log)")
    return CheckResult(spec.name, verdict.status, verdict.summary, spec.blocking, verdict.details)


@dataclass(frozen=True)
class RunMeta:
    commit: str | None
    run_url: str | None
    duration: str | None
    setup_failed: bool


def run_meta(env: Mapping[str, str], now: float) -> RunMeta:
    sha = (env.get("CI_COMMIT_SHA") or env.get("GITHUB_SHA") or "").strip().lower()
    commit = sha[:7] if COMMIT_SHA.fullmatch(sha) else None

    server = env.get("GITHUB_SERVER_URL", "")
    repository = env.get("GITHUB_REPOSITORY", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    run_url = None
    if (
        SERVER_URL.fullmatch(server)
        and REPOSITORY.fullmatch(repository)
        and DIGITS.fullmatch(run_id)
    ):
        run_url = f"{server}/{repository}/actions/runs/{run_id}"
        attempt = env.get("GITHUB_RUN_ATTEMPT", "")
        if DIGITS.fullmatch(attempt) and attempt != "1":
            run_url += f"/attempts/{attempt}"

    started = env.get("CI_STARTED_AT", "")
    duration = format_duration(now - int(started)) if DIGITS.fullmatch(started) else None
    setup_failed = env.get("OUTCOME_INSTALL", "") in {FAILURE, "skipped"}
    return RunMeta(commit, run_url, duration, setup_failed)


def headline(results: Sequence[CheckResult], meta: RunMeta) -> str:
    blocking = [result for result in results if result.blocking]
    total = len(blocking)
    counts = Counter(result.status for result in blocking)
    failed, skipped = counts[Status.FAILED], counts[Status.SKIPPED]
    warned = sum(1 for result in results if result.status is Status.WARNING)
    parts = []
    if meta.setup_failed:
        parts.append(f"{Status.FAILED.value} Falló la preparación del entorno")
    if failed:
        parts.append(f"{Status.FAILED.value} {failed} de {total} fallaron")
    elif not meta.setup_failed:
        parts.append(f"{Status.PASSED.value} {counts[Status.PASSED]} de {total} pasaron")
    if skipped:
        parts.append(f"{Status.SKIPPED.value} {skipped} no corrieron")
    if warned:
        parts.append(f"{Status.WARNING.value} {warned} con advertencias")
    return " · ".join(parts)


def render_detail(detail: Detail, line_limit: int, run_url: str | None) -> str:
    lines: list[str] = []
    shown = 0
    for entry in detail.entries:
        entry_lines = [clean_line(line) for line in entry.splitlines()] or [""]
        room = line_limit - len(lines)
        if room <= 0 or (lines and len(entry_lines) > room):
            break
        lines.extend(entry_lines[:room])
        shown += 1
    remaining = len(detail.entries) - shown + detail.hidden
    parts = [f"<details><summary>{html_text(detail.title)}</summary>", "", code_block(lines)]
    if remaining:
        more = f"… y {remaining} más"
        if run_url:
            more += f" · [log completo]({run_url})"
        parts += ["", more]
    parts += ["", "</details>"]
    return "\n".join(parts)


def _detail_order(result: CheckResult) -> int:
    # Primero los tests que fallan y al final las advertencias, como en el ejemplo de la spec.
    return {TESTS: 0, WARNINGS: 2}.get(result.name, 1)


def render(results: Sequence[CheckResult], meta: RunMeta, line_limit: int | None) -> str:
    out = [MARKER, f"## {TITLE} · {headline(results, meta)}"]
    meta_parts = []
    if meta.commit:
        meta_parts.append(f"Commit `{meta.commit}`")
    if meta.run_url:
        meta_parts.append(f"[Ver run]({meta.run_url})")
    if meta.duration:
        meta_parts.append(meta.duration)
    if meta_parts:
        out.append(" · ".join(meta_parts))
    out += ["", "| Verificación | Estado | Detalle |", "| --- | --- | --- |"]
    out += [
        f"| {result.name} | {result.status.value} | {md_inline(result.summary)} |"
        for result in results
    ]
    with_details = [result for result in results if result.details]
    if with_details and line_limit is None:
        out += ["", DETAILS_OMITTED]
    elif line_limit is not None:
        for result in sorted(with_details, key=_detail_order):
            out += ["", *(render_detail(d, line_limit, meta.run_url) for d in result.details)]
    return "\n".join(out) + "\n"


def _coverage_min(env: Mapping[str, str]) -> float:
    try:
        return float(env.get("CI_COVERAGE_MIN") or DEFAULT_COVERAGE_MIN)
    except ValueError:
        return DEFAULT_COVERAGE_MIN


def build_report(env: Mapping[str, str], report_dir: Path, base_dir: Path, now: float) -> str:
    outcomes = {key: env.get(f"OUTCOME_{key.upper()}", "").strip().lower() for key in OUTCOME_KEYS}
    ctx = Context(report_dir, outcomes, _coverage_min(env), base_dir)
    results = [run_check(spec, ctx) for spec in CHECKS]
    meta = run_meta(env, now)
    for line_limit in DETAIL_LINE_LIMITS:
        markdown = render(results, meta, line_limit)
        if len(markdown) <= MAX_REPORT_CHARS:
            return markdown
    return render(results, meta, None)


def fallback_report() -> str:
    return (
        f"{MARKER}\n"
        f"## {TITLE} · {Status.WARNING.value} No se pudo generar el reporte\n\n"
        "El script del reporte falló; el detalle está en el log del run. "
        "El check obligatorio no depende de este comentario.\n"
    )


def write_outputs(markdown: str, targets: Iterable[tuple[Path, str]]) -> None:
    for path, mode in targets:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open(mode, encoding="utf-8") as handle:
                handle.write(markdown)
        except OSError:
            traceback.print_exc(file=sys.stderr)


def main(environ: Mapping[str, str] | None = None, now: float | None = None) -> int:
    env = os.environ if environ is None else environ
    report_dir = Path(env.get("CI_REPORT_DIR") or DEFAULT_REPORT_DIR)
    current = time.time() if now is None else now
    try:
        markdown = build_report(env, report_dir, Path.cwd().resolve(), current)
    except Exception:  # El script nunca hace fallar el job.
        traceback.print_exc(file=sys.stderr)
        markdown = fallback_report()
    targets = [(report_dir / REPORT_FILE, "w")]
    step_summary = env.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        targets.append((Path(step_summary), "a"))
    write_outputs(markdown, targets)
    print(f"ci_report: reporte escrito en {report_dir / REPORT_FILE}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
