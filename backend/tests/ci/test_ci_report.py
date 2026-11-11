"""Pruebas del reporte del CI (scripts/ci_report.py)."""

import json
import re
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts import ci_report
from scripts.ci_report import Context, Detail, WarningRecorder

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_800_000_134.0
RUN_URL = "https://github.com/acme/backoffice/actions/runs/123"
CHECK_KEYS = ("ruff_lint", "ruff_format", "mypy", "migrations", "tests", "coverage", "openapi")
ROW_NAMES = (
    "Ruff (lint)",
    "Ruff (formato)",
    "Mypy",
    "Migraciones",
    "Tests",
    "Cobertura",
    "Advertencias",
    "Contrato OpenAPI",
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Carpeta de trabajo como ``backend/`` en CI: las rutas se muestran relativas a ella."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def report_dir(workspace: Path) -> Path:
    path = workspace / ".ci-report"
    path.mkdir()
    return path


def use_fixture(name: str, report_dir: Path) -> None:
    base = report_dir.parent.as_posix()
    for source in (FIXTURES / name).iterdir():
        text = source.read_text(encoding="utf-8").replace("@BASE@", base)
        (report_dir / source.name).write_text(text, encoding="utf-8")


def github_env(report_dir: Path, outcome: str = "success", **outcomes: str) -> dict[str, str]:
    env = {
        "CI_REPORT_DIR": str(report_dir),
        "CI_COMMIT_SHA": "abc1234def5678abc1234def5678abc1234def56",
        "CI_STARTED_AT": str(int(NOW) - 134),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "acme/backoffice",
        "GITHUB_RUN_ID": "123",
        "GITHUB_STEP_SUMMARY": str(report_dir.parent / "step-summary.md"),
        "OUTCOME_INSTALL": "success",
    }
    for key in CHECK_KEYS:
        env[f"OUTCOME_{key.upper()}"] = outcomes.get(key, outcome)
    return env


def run_report(env: dict[str, str]) -> str:
    assert ci_report.main(env, now=NOW) == 0
    return (Path(env["CI_REPORT_DIR"]) / "report.md").read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def row(markdown: str, name: str) -> tuple[str, str]:
    for line in markdown.splitlines():
        if line.startswith(f"| {name} |"):
            cells = re.split(r"(?<!\\)\|", line)[1:-1]
            return cells[1].strip(), cells[2].strip()
    raise AssertionError(f"El reporte no tiene la fila {name!r}")


def detail_block(markdown: str, title: str) -> str:
    start = markdown.index(f"<details><summary>{title}")
    # El cierre real va solo en su línea; un "</details>" dentro del código no cuenta.
    end = re.compile(r"^</details>$", re.MULTILINE).search(markdown, start)
    assert end is not None
    return markdown[start : end.start()]


def code_lines(block: str) -> list[str]:
    match = re.search(r"^(`{3,})\n(.*?)\n\1$", block, re.MULTILINE | re.DOTALL)
    assert match is not None, block
    return match.group(2).splitlines()


def outside_code(markdown: str) -> str:
    return re.sub(r"^(`{3,})\n.*?\n\1$", "", markdown, flags=re.MULTILINE | re.DOTALL)


def ruff_item(code: str | None, path: str, line: int, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "filename": path,
        "location": {"row": line, "column": 1},
        "message": message,
    }


def junit(cases: str) -> str:
    return f'<testsuites><testsuite name="pytest" time="1.5">{cases}</testsuite></testsuites>'


# --- Casos de la spec ----------------------------------------------------------------------


def test_all_green(report_dir: Path) -> None:
    use_fixture("green", report_dir)
    env = github_env(report_dir)

    markdown = run_report(env)

    lines = markdown.splitlines()
    assert lines[0] == ci_report.MARKER
    assert lines[1] == "## Backend CI · ✅ 7 de 7 pasaron"
    assert lines[2] == f"Commit `abc1234` · [Ver run]({RUN_URL}) · 2 min 14 s"
    assert [row(markdown, name)[0] for name in ROW_NAMES] == ["✅"] * 8
    assert row(markdown, "Ruff (lint)")[1] == "Sin errores"
    assert row(markdown, "Tests")[1] == "4 pasan · 0 fallan · 0 saltados (4 en 2 min 14 s)"
    assert row(markdown, "Cobertura")[1] == "98,31 % (mínimo 95 %)"
    assert row(markdown, "Advertencias")[1] == "Sin advertencias"
    assert row(markdown, "Contrato OpenAPI")[1] == "Al día"
    assert "<details>" not in markdown
    assert Path(env["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8") == markdown


def test_failures_and_warnings_together(report_dir: Path) -> None:
    use_fixture("failing", report_dir)

    markdown = run_report(github_env(report_dir, outcome="failure"))

    assert markdown.splitlines()[1] == "## Backend CI · ❌ 7 de 7 fallaron · ⚠️ 1 con advertencias"
    assert row(markdown, "Ruff (lint)") == ("❌", "3 errores en 2 archivos")
    assert row(markdown, "Ruff (formato)") == ("❌", "2 archivos sin formatear")
    assert row(markdown, "Mypy") == ("❌", "2 errores en 2 archivos")
    assert row(markdown, "Migraciones") == ("❌", "Faltan migraciones en: crm, documents")
    assert row(markdown, "Tests") == ("❌", "2 pasan · 3 fallan · 1 saltado (6 en 2 min 14 s)")
    assert row(markdown, "Cobertura") == ("❌", "93,10 % · mínimo 95 % · con tests fallidos")
    assert row(markdown, "Advertencias") == (
        "⚠️",
        "4 (DeprecationWarning: 3, RuntimeWarning: 1)",
    )
    assert row(markdown, "Contrato OpenAPI") == ("❌", "3 advertencias del esquema")
    # Primero los tests que fallan y al final las advertencias.
    titles = re.findall(r"<summary>(.*?)</summary>", markdown)
    assert titles[0] == "Tests que fallan (3)"
    assert titles[-1] == "Advertencias (4)"
    assert len(titles) == 8


def test_failure_details(report_dir: Path) -> None:
    use_fixture("failing", report_dir)
    # Con dos fuentes en --cov, coverage.xml no dice a cuál pertenece cada archivo.
    (report_dir.parent / "apps" / "crm").mkdir(parents=True)
    (report_dir.parent / "apps" / "crm" / "services.py").touch()

    markdown = run_report(github_env(report_dir, outcome="failure"))

    assert code_lines(detail_block(markdown, "Ruff (lint): 3 errores (F401: 2, E501: 1)")) == [
        "F401  apps/crm/views.py:1:8  `os` imported but unused",
        "F401  apps/crm/views.py:2:8  `sys` imported but unused",
        "E501  apps/crm/services.py:40:101  Line too long (111 > 100)",
    ]
    assert code_lines(detail_block(markdown, "Ruff (formato)")) == [
        "apps/crm/serializers.py",
        "apps/documents/services.py",
    ]
    assert code_lines(detail_block(markdown, "Mypy")) == [
        'apps/crm/services.py:57  [return-value] Incompatible return value type (got "int", '
        'expected "str")',
        'apps/documents/views.py:120  [union-attr] Item "None" of "User | None" has no '
        'attribute "email"',
    ]
    assert code_lines(detail_block(markdown, "Migraciones")) == [
        "Migrations for 'crm':",
        "  apps/crm/migrations/0006_client_nickname.py",
        "    + Add field nickname to client",
        "Migrations for 'documents':",
        "  apps/documents/migrations/0009_alter_documentfile_status.py",
        "    ~ Alter field status on documentfile",
    ]
    assert code_lines(detail_block(markdown, "Tests que fallan")) == [
        "tests.crm.test_clients.TestCreate::test_rejects_duplicate_email",
        "    AssertionError: assert 201 == 400",
        "tests.documents.test_upload::test_scan_marks_infected[eicar]",
        "    RuntimeError: clamd no responde",
        "tests.identity.test_login::test_rate_limit",
        "    failed on setup with \"KeyError: 'default'\"",
    ]
    # Sin migraciones; empates por más sentencias; las rutas se resuelven si el archivo existe.
    assert code_lines(detail_block(markdown, "Cobertura: 5 módulos con menos cobertura")) == [
        " 60,00 %  apps/crm/services.py (10 sentencias)",
        " 75,00 %  documents/views.py (4 sentencias)",
        " 80,00 %  identity/models/user.py (5 sentencias)",
        " 90,00 %  partners/services.py (10 sentencias)",
        "100,00 %  crm/models.py (3 sentencias)",
    ]
    assert code_lines(detail_block(markdown, "Advertencias")) == [
        "DeprecationWarning (3) · más frecuente, 2 veces:",
        "    apps/identity/tokens.py:41: datetime.datetime.utcnow() is deprecated and scheduled "
        "for removal in a future version.",
        "RuntimeWarning (1) · más frecuente, 1 vez:",
        "    django/db/models/fields/__init__.py:1665: DateTimeField Application.created_at "
        "received a naive datetime (2026-01-01 00:00:00) while time zone support is active.",
    ]
    spectacular = code_lines(detail_block(markdown, "Contrato OpenAPI"))
    assert len(spectacular) == 2
    assert spectacular[0].startswith("/app/apps/crm/serializers.py:41: Warning [ClientViewSet")


def test_setup_failure_marks_every_check_as_not_run(workspace: Path) -> None:
    env = github_env(workspace / ".ci-report", outcome="skipped")
    env["OUTCOME_INSTALL"] = "failure"

    markdown = run_report(env)

    assert markdown.splitlines()[1] == (
        "## Backend CI · ❌ Falló la preparación del entorno · ⏭️ 7 no corrieron"
    )
    assert [row(markdown, name) for name in ROW_NAMES] == [("⏭️", "No corrió")] * 8


def test_step_that_did_not_run(report_dir: Path) -> None:
    use_fixture("green", report_dir)
    env = github_env(report_dir, tests="failure", coverage="skipped", mypy="cancelled")
    (report_dir / "pytest.xml").unlink()

    markdown = run_report(env)

    assert markdown.splitlines()[1] == ("## Backend CI · ❌ 1 de 7 fallaron · ⏭️ 2 no corrieron")
    assert row(markdown, "Mypy") == ("⏭️", "Cancelado")
    assert row(markdown, "Tests") == ("❌", "Falló sin resultados (ver el log)")
    assert row(markdown, "Cobertura") == ("⏭️", "Sin datos de cobertura")


def test_coverage_measured_after_failed_tests(report_dir: Path) -> None:
    use_fixture("green", report_dir)

    markdown = run_report(github_env(report_dir, tests="failure"))

    assert row(markdown, "Cobertura") == ("✅", "98,31 % · mínimo 95 % · con tests fallidos")


def test_long_output_is_truncated(report_dir: Path) -> None:
    codes = ["E501", "F401", "F841", "B006", "UP035", "I001", "E711"]
    long_message = "x" * 400
    write_json(
        report_dir / "ruff.json",
        [
            ruff_item(codes[i % 7], f"{report_dir.parent}/apps/m{i:03}.py", i, long_message)
            for i in range(120)
        ],
    )
    failure = '<testcase classname="tests.t" name="test_{0:02}"><failure message="boom {0}"/>'
    cases = "".join(failure.format(i) + "</testcase>" for i in range(30))
    (report_dir / "pytest.xml").write_text(junit(cases), encoding="utf-8")

    markdown = run_report(github_env(report_dir, ruff_lint="failure", tests="failure"))

    # El título muestra las 5 reglas más frecuentes.
    ruff_block = detail_block(
        markdown, "Ruff (lint): 120 errores (E501: 18, B006: 17, E711: 17, F401: 17, F841: 17, …)"
    )
    lines = code_lines(ruff_block)
    assert len(lines) == 50
    assert all(len(line) <= ci_report.MAX_LINE_CHARS for line in lines)
    assert lines[0].endswith("x…")
    assert f"… y 70 más · [log completo]({RUN_URL})" in ruff_block
    tests_block = detail_block(markdown, "Tests que fallan (30)")
    assert len(code_lines(tests_block)) == 40
    assert "… y 10 más" in tests_block


def test_failing_test_without_message(report_dir: Path) -> None:
    (report_dir / "pytest.xml").write_text(
        '<testsuite name="pytest"><testcase name="test_bare" time="0.5"><failure/></testcase>'
        "</testsuite>",
        encoding="utf-8",
    )

    markdown = run_report(github_env(report_dir, tests="failure"))

    assert row(markdown, "Tests")[1] == "0 pasan · 1 falla · 0 saltados (1 en 0 s)"
    assert code_lines(detail_block(markdown, "Tests que fallan (1)")) == ["test_bare"]


def test_report_shrinks_details_to_fit(report_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_json(
        report_dir / "ruff.json",
        [ruff_item("E501", "apps/a.py", i, "y" * 150) for i in range(120)],
    )
    env = github_env(report_dir, ruff_lint="failure")
    env.pop("GITHUB_SERVER_URL")

    monkeypatch.setattr(ci_report, "MAX_REPORT_CHARS", 6_000)
    markdown = run_report(env)
    assert len(markdown) <= 6_000
    assert len(code_lines(detail_block(markdown, "Ruff (lint)"))) == 20
    assert "… y 100 más\n" in markdown  # Sin URL del run no hay enlace al log.

    monkeypatch.setattr(ci_report, "MAX_REPORT_CHARS", 500)
    markdown = run_report(env)
    assert "<details>" not in markdown
    assert ci_report.DETAILS_OMITTED in markdown


def test_special_characters_are_escaped(report_dir: Path) -> None:
    hostile = "uses ``` and <!-- ci-report:backend --> </details> <script>x</script>"
    write_json(
        report_dir / "ruff.json",
        [ruff_item("X|<i>", "apps/a.py", 1, f"\x1b[31m{hostile}\x00\x1b[0m")],
    )
    (report_dir / "migrations.txt").write_text(
        "Migrations for 'crm|<b>x</b>':\n  apps/crm/migrations/0007.py\n", encoding="utf-8"
    )
    write_json(
        report_dir / "warnings.json",
        [{"category": "Odd|Warning*", "message": "`m`", "filename": "a.py", "lineno": 1}],
    )
    env = github_env(report_dir, ruff_lint="failure", migrations="failure")

    markdown = run_report(env)

    assert row(markdown, "Migraciones")[1] == ("Faltan migraciones en: crm\\|&lt;b&gt;x&lt;/b&gt;")
    assert row(markdown, "Advertencias")[1] == "1 (Odd\\|Warning\\*: 1)"
    table = [line for line in markdown.splitlines() if line.startswith("| ")]
    assert len(table) == 10  # Encabezado, separador y 8 filas: ninguna se partió.
    assert all(len(re.findall(r"(?<!\\)\|", line)) == 4 for line in table)
    block = detail_block(markdown, "Ruff (lint): 1 error (X|&lt;i&gt;: 1)")
    assert code_lines(block) == [f"X|<i>  apps/a.py:1:1  {hostile}"]
    assert "\n````\n" in block
    rest = outside_code(markdown)
    assert "<script>" not in rest
    assert rest.count(ci_report.MARKER) == 1
    assert rest.count("<details>") == rest.count("</details>") == 3


# --- Contrato OpenAPI ----------------------------------------------------------------------


def operation(description: str = "") -> dict[str, Any]:
    return {"responses": {"200": {"description": description}}}


COMMITTED = {
    "info": {"version": "1.0.0"},
    "paths": {
        "/api/v1/clients": {"get": operation(), "post": operation(), "parameters": []},
        "/api/v1/legacy": {"get": operation()},
    },
    "components": {"schemas": {"Client": {"type": "object"}, "Legacy": {"type": "object"}}},
}


def change_routes_and_schemas(contract: dict[str, Any]) -> None:
    contract["paths"]["/api/v1/clients"] = {"get": operation("cambió"), "post": operation()}
    contract["paths"]["/api/v1/clients/{id}"] = {"delete": operation(), "patch": operation()}
    del contract["paths"]["/api/v1/legacy"]
    contract["components"]["schemas"]["Client"] = {"type": "string"}
    del contract["components"]["schemas"]["Legacy"]
    contract["components"]["schemas"]["Note"] = {"type": "object"}


def remove_one_route(contract: dict[str, Any]) -> None:
    del contract["paths"]["/api/v1/legacy"]["get"]


def change_only_info(contract: dict[str, Any]) -> None:
    contract["info"]["version"] = "1.1.0"


@pytest.mark.parametrize(
    ("change", "summary", "entries"),
    [
        (
            change_routes_and_schemas,
            "Desactualizado: 2 rutas nuevas · 1 ruta quitada · 1 ruta cambiada · "
            "1 esquema nuevo · 1 esquema quitado · 1 esquema cambiado",
            [
                "~ GET /api/v1/clients",
                "+ DELETE /api/v1/clients/{id}",
                "+ PATCH /api/v1/clients/{id}",
                "- GET /api/v1/legacy",
                "~ esquema Client",
                "- esquema Legacy",
                "+ esquema Note",
            ],
        ),
        (remove_one_route, "Desactualizado: 1 ruta quitada", ["- GET /api/v1/legacy"]),
        (
            change_only_info,
            "Desactualizado",
            ["Cambios fuera de paths y components.schemas"],
        ),
    ],
)
def test_outdated_contract_lists_what_changed(
    report_dir: Path, change: Callable[[dict[str, Any]], None], summary: str, entries: list[str]
) -> None:
    generated = json.loads(json.dumps(COMMITTED))
    change(generated)
    write_json(report_dir / "openapi.committed.json", COMMITTED)
    write_json(report_dir / "openapi.generated.json", generated)

    markdown = run_report(github_env(report_dir, openapi="failure"))

    assert row(markdown, "Contrato OpenAPI") == ("❌", summary)
    lines = code_lines(detail_block(markdown, "Contrato OpenAPI: cambios sin regenerar"))
    assert lines == entries  # Sin el diff --stat: la lista ya dice qué cambió.


def test_schema_errors_without_summary(report_dir: Path) -> None:
    (report_dir / "spectacular.txt").write_text(
        "Error [ClientViewSet]: bad\n\x1b[0;33mWarning: odd\x1b[0m\n", encoding="utf-8"
    )

    markdown = run_report(github_env(report_dir, openapi="failure"))

    assert row(markdown, "Contrato OpenAPI")[1] == (
        "1 error del esquema y 1 advertencia del esquema"
    )
    block = detail_block(markdown, "Contrato OpenAPI: avisos de spectacular")
    assert code_lines(block) == ["Error [ClientViewSet]: bad", "Warning: odd"]


# --- Tolerancia a fallos -------------------------------------------------------------------


def test_missing_files_after_failed_steps(workspace: Path) -> None:
    markdown = run_report(github_env(workspace / ".ci-report", outcome="failure"))

    assert row(markdown, "Ruff (lint)")[1] == "Falló sin errores reportados (ver el log)"
    assert row(markdown, "Ruff (formato)")[1] == "Falló sin archivos reportados (ver el log)"
    assert row(markdown, "Mypy")[1] == "Falló (ver el log)"
    assert row(markdown, "Migraciones")[1] == "Falló (ver el log)"
    assert row(markdown, "Cobertura")[1] == (
        "Por debajo del mínimo (95 %) o sin datos (ver el log) · con tests fallidos"
    )
    # Si los tests corrieron y no hay warnings.json, no hubo warnings.
    assert row(markdown, "Advertencias") == ("✅", "Sin advertencias")
    assert row(markdown, "Contrato OpenAPI")[1] == "Falló la generación del contrato (ver el log)"
    assert "<details>" not in markdown


def test_successful_steps_without_result_files(workspace: Path) -> None:
    markdown = run_report(github_env(workspace / ".ci-report"))

    assert row(markdown, "Tests") == ("✅", "Pasaron (sin resultados JUnit)")
    assert row(markdown, "Cobertura") == ("✅", "Sobre el mínimo (95 %)")


def test_unrecognized_output_shows_its_tail(report_dir: Path) -> None:
    crash = "Traceback (most recent call last):\n  File 'x.py', line 1\nKeyError: 'boom'\n"
    for name in ("mypy.txt", "migrations.txt", "spectacular.txt"):
        (report_dir / name).write_text(crash, encoding="utf-8")
    write_json(
        report_dir / "ruff-format.json",
        [
            ruff_item("unformatted", "apps/a.py", 1, "File would be reformatted"),
            ruff_item(None, "apps/b.py", 3, "Expected an expression"),
            {"code": "E1", "filename": "apps/c.py", "location": None},
            "not-a-diagnostic",
        ],
    )
    env = github_env(report_dir, outcome="failure", tests="success", coverage="success")

    markdown = run_report(env)

    for title in ("Mypy: salida", "Migraciones: salida", "Contrato OpenAPI: salida"):
        assert code_lines(detail_block(markdown, title))[-1] == "KeyError: 'boom'"
    assert row(markdown, "Ruff (formato)")[1] == "1 archivo sin formatear · 2 errores"
    assert code_lines(detail_block(markdown, "Ruff (formato)")) == [
        "apps/a.py",
        "syntax-error  apps/b.py:3:1  Expected an expression",
        "E1  apps/c.py:0:0",
    ]


def test_unreadable_files_do_not_break_the_report(report_dir: Path) -> None:
    (report_dir / "pytest.xml").write_text("<oops", encoding="utf-8")
    (report_dir / "coverage.xml").write_text("<oops", encoding="utf-8")
    (report_dir / "warnings.json").write_text("{", encoding="utf-8")
    (report_dir / "ruff.json").write_text("{}", encoding="utf-8")
    env = github_env(report_dir, tests="failure", ruff_lint="failure")

    markdown = run_report(env)

    unreadable = "No se pudo leer el detalle (ver el log)"
    assert row(markdown, "Tests") == ("❌", unreadable)
    assert row(markdown, "Ruff (lint)") == ("❌", unreadable)
    assert row(markdown, "Cobertura") == ("✅", unreadable)
    assert row(markdown, "Advertencias") == ("⚠️", unreadable)
    assert row(markdown, "Mypy") == ("✅", "Sin errores")


def test_non_list_warnings_file_is_unreadable(report_dir: Path) -> None:
    write_json(report_dir / "warnings.json", {"category": "DeprecationWarning"})

    markdown = run_report(github_env(report_dir))

    assert row(markdown, "Advertencias") == ("⚠️", "No se pudo leer el detalle (ver el log)")


def test_unexpected_error_writes_a_minimal_report(
    report_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(ci_report, "build_report", explode)
    env = github_env(report_dir)

    markdown = run_report(env)

    assert markdown == ci_report.fallback_report()
    assert markdown.startswith(ci_report.MARKER)
    assert Path(env["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8") == markdown


def test_write_errors_are_ignored(report_dir: Path) -> None:
    env = github_env(report_dir)
    env["GITHUB_STEP_SUMMARY"] = str(report_dir)  # Una carpeta: no se puede abrir.

    markdown = run_report(env)

    assert markdown.startswith(ci_report.MARKER)


def test_defaults_without_github_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # En CI estas variables existen; sin ellas el script usa .ci-report y omite los datos del run.
    for name in (
        "CI_REPORT_DIR",
        "CI_COMMIT_SHA",
        "CI_STARTED_AT",
        "CI_COVERAGE_MIN",
        "GITHUB_SHA",
        "GITHUB_SERVER_URL",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_STEP_SUMMARY",
        *(f"OUTCOME_{key.upper()}" for key in ci_report.OUTCOME_KEYS),
    ):
        monkeypatch.delenv(name, raising=False)

    assert ci_report.main() == 0

    markdown = (workspace / ".ci-report" / "report.md").read_text(encoding="utf-8")
    assert markdown.splitlines()[1] == "## Backend CI · ✅ 0 de 7 pasaron · ⏭️ 7 no corrieron"
    assert markdown.splitlines()[2] == ""


# --- Warnings de pytest --------------------------------------------------------------------


def make_warning(
    message: str, category: type[Warning] = DeprecationWarning
) -> warnings.WarningMessage:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn(message, category, stacklevel=1)
    return caught[0]


def test_warning_recorder_only_exists_with_report_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI_REPORT_DIR", raising=False)
    assert WarningRecorder.from_env() is None
    assert WarningRecorder.from_env({"CI_REPORT_DIR": ""}) is None
    recorder = WarningRecorder.from_env({"CI_REPORT_DIR": str(tmp_path)})
    assert recorder is not None
    assert recorder.report_dir == tmp_path


def test_warning_recorder_writes_once_at_the_end(tmp_path: Path) -> None:
    recorder = WarningRecorder(tmp_path / ".ci-report")
    recorder.record(make_warning("viejo"), nodeid="tests/x.py::test_a", when="runtest")
    recorder.record(make_warning("raro", RuntimeWarning), nodeid="", when="collect")
    path = tmp_path / ".ci-report" / "warnings.json"
    assert not path.exists()  # Acumula en memoria hasta el final de la sesión.

    assert recorder.write() == path

    records = json.loads(path.read_text(encoding="utf-8"))
    assert [(r["category"], r["message"], r["nodeid"], r["when"]) for r in records] == [
        ("DeprecationWarning", "viejo", "tests/x.py::test_a", "runtest"),
        ("RuntimeWarning", "raro", "", "collect"),
    ]
    assert records[0]["filename"] == __file__
    assert isinstance(records[0]["lineno"], int)


def test_warning_recorder_survives_write_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    recorder = WarningRecorder(blocker / ".ci-report")

    assert recorder.write() is None
    assert "no se pudo escribir" in capsys.readouterr().err


# --- Piezas sueltas ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(-5, "0 s"), (45.4, "45 s"), (134, "2 min 14 s"), (3720, "1 h 2 min")],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert ci_report.format_duration(seconds) == expected


def test_number_formats() -> None:
    assert ci_report.format_percent(98.3107) == "98,31 %"
    assert ci_report.format_minimum(95.0) == "95 %"
    assert ci_report.format_minimum(92.5) == "92,5 %"
    assert ci_report.md_inline("a|b <c> *d*\nnext & `e`") == (
        "a\\|b &lt;c&gt; \\*d\\* next &amp; \\`e\\`"
    )


def test_run_metadata_rejects_unexpected_values() -> None:
    meta = ci_report.run_meta(
        {
            "GITHUB_SHA": "not-a-sha",
            "GITHUB_SERVER_URL": "http://github.com",
            "GITHUB_REPOSITORY": "acme/backoffice",
            "GITHUB_RUN_ID": "123",
            "CI_STARTED_AT": "soon",
        },
        NOW,
    )
    assert (meta.commit, meta.run_url, meta.duration) == (None, None, None)


def test_run_metadata_with_retry_and_github_sha() -> None:
    meta = ci_report.run_meta(
        {
            "GITHUB_SHA": "ABCDEF1234567",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "acme/backoffice",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
        },
        NOW,
    )
    assert meta.commit == "abcdef1"
    assert meta.run_url == f"{RUN_URL}/attempts/2"


@pytest.mark.parametrize(("value", "expected"), [("90", "mínimo 90 %"), ("x", "mínimo 95 %")])
def test_coverage_minimum_from_environment(report_dir: Path, value: str, expected: str) -> None:
    use_fixture("green", report_dir)
    env = github_env(report_dir)
    env["CI_COVERAGE_MIN"] = value

    assert expected in row(run_report(env), "Cobertura")[1]


def test_coverage_with_one_source_and_no_lines(tmp_path: Path) -> None:
    (tmp_path / "coverage.xml").write_text(
        '<coverage lines-valid="0" lines-covered="0"><sources><source>/w/apps</source>'
        '</sources><packages><package><classes><class filename="crm/x.py"><lines>'
        '<line number="1" hits="x"/></lines></class></classes></package></packages></coverage>',
        encoding="utf-8",
    )
    ctx = Context(tmp_path, {}, 95.0, tmp_path)

    data = ci_report.load_coverage(ctx)

    assert data is not None
    total, modules = data
    assert total == 100.0
    assert [(m.path, m.percent) for m in modules] == [("/w/apps/crm/x.py", 0.0)]


def test_detail_entry_longer_than_the_limit_is_cut() -> None:
    detail = Detail("Salida", ["\n".join(f"línea {i}" for i in range(60)), "", "otra"])

    rendered = ci_report.render_detail(detail, 50, None)

    lines = code_lines(rendered)
    assert len(lines) == 50
    assert lines[-1] == "línea 49"
    assert "… y 2 más" in rendered
