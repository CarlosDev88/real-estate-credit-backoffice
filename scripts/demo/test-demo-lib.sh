#!/usr/bin/env bash
# Pruebas de scripts/demo/demo-lib.sh, sin Docker y en un directorio temporal.
# Uso: bash scripts/demo/test-demo-lib.sh   (sale con 1 si alguna falla)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/demo/demo-lib.sh
. "$HERE/demo-lib.sh"
NO_COLOR=1 demo_color_init

PASSED=0
FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

check() { # check "nombre" condición...
  local name="$1"
  shift
  if "$@"; then
    PASSED=$((PASSED + 1))
  else
    FAILED=$((FAILED + 1))
    printf 'FALLA: %s\n' "$name"
  fi
}
equals() { [ "$1" = "$2" ]; }
returns() { # returns CÓDIGO comando...
  local expected="$1" rc=0
  shift
  "$@" >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq "$expected" ]
}
file_hash() { cksum <"$1"; }
crlf_lines() { tr -cd '\r' <"$1" | wc -c | tr -d ' '; }
line_count() { wc -l <"$1" | tr -d ' '; }

# Un .env.example de mentira, con CRLF como el real; nunca se lee el del repo.
make_example() { # make_example DIRECTORIO
  mkdir -p "$1"
  printf '# Demo\r\nDJANGO_SECRET_KEY=cambiar\r\nDJANGO_DEBUG=False\r\nPOSTGRES_DB=mvp_credit\r\n# AUTH_JWT_SIGNING_KEY=comentada\r\nAUTH_JWT_SIGNING_KEY=cambiar\r\n' >"$1/.env.example"
}

# --- Argumentos ----------------------------------------------------------------------
demo_parse_args
check "sin opciones: start" equals "$DEMO_ACTION" "start"
check "sin opciones: modo simple" equals "$DEMO_FULL" "0"
demo_parse_args --full
check "--full: start completo" equals "$DEMO_ACTION:$DEMO_FULL" "start:1"
demo_parse_args --stop
check "--stop" equals "$DEMO_ACTION" "stop"
demo_parse_args --reset
check "--reset" equals "$DEMO_ACTION" "reset"
demo_parse_args --help
check "--help" equals "$DEMO_ACTION" "help"
check "--stop con --reset es un error de uso" returns "$DEMO_EXIT_USAGE" demo_parse_args --stop --reset
check "--reset con --stop es un error de uso" returns "$DEMO_EXIT_USAGE" demo_parse_args --reset --stop
check "opción desconocida es un error de uso" returns "$DEMO_EXIT_USAGE" demo_parse_args --borrar-todo

# --- Secretos ------------------------------------------------------------------------
s1="$(demo_generate_secret)"
s2="$(demo_generate_secret)"
check "el secreto tiene 48 bytes en base64 de URL" demo_secret_ok "$s1"
check "el secreto tiene exactamente 64 caracteres" equals "${#s1}" "64"
check "dos secretos son distintos" [ "$s1" != "$s2" ]
check "un secreto corto no es válido" returns 1 demo_secret_ok "abc"
check "un secreto con espacios no es válido" returns 1 demo_secret_ok "$(printf 'a%.0s' $(seq 1 63)) "

# --- demo_set_env_value y demo_get_env_value -----------------------------------------
f="$WORK/lf.env"
printf 'A=1\nB=2\n' >"$f"
demo_set_env_value "$f" B 9
check "reemplaza una clave (LF)" equals "$(cat "$f")" "$(printf 'A=1\nB=9')"
demo_set_env_value "$f" C 3
check "agrega una clave que falta (LF)" equals "$(demo_get_env_value "$f" C)" "3"
check "no agrega CR a un archivo LF" equals "$(crlf_lines "$f")" "0"

f="$WORK/crlf.env"
printf 'A=1\r\n# B=comentada\r\nB=2\r\n' >"$f"
demo_set_env_value "$f" B 9
check "reemplaza una clave y conserva CRLF" equals "$(crlf_lines "$f")" "3"
check "no toca la línea comentada" grep -q '^# B=comentada' "$f"
check "lee el valor sin el CR" equals "$(demo_get_env_value "$f" B)" "9"
demo_set_env_value "$f" D 4
check "agrega con CRLF en un archivo CRLF" equals "$(crlf_lines "$f")" "4"
check "valor por omisión si falta la clave" equals "$(demo_get_env_value "$f" NADA 8000)" "8000"
check "valor por omisión si falta el archivo" equals "$(demo_get_env_value "$WORK/no-existe" X 3000)" "3000"

# --- demo_ensure_env -----------------------------------------------------------------
dir="$WORK/backend-nuevo"
make_example "$dir"
check "crea backend/.env si no existe" returns 0 demo_ensure_env "$dir"
check "el .env existe" [ -f "$dir/.env" ]
key1="$(demo_get_env_value "$dir/.env" DJANGO_SECRET_KEY)"
key2="$(demo_get_env_value "$dir/.env" AUTH_JWT_SIGNING_KEY)"
check "DJANGO_SECRET_KEY es nueva y fuerte" demo_secret_ok "$key1"
check "AUTH_JWT_SIGNING_KEY es nueva y fuerte" demo_secret_ok "$key2"
check "las dos claves son distintas" [ "$key1" != "$key2" ]
check "DJANGO_DEBUG=True" equals "$(demo_get_env_value "$dir/.env" DJANGO_DEBUG)" "True"
check "conserva las demás variables" equals "$(demo_get_env_value "$dir/.env" POSTGRES_DB)" "mvp_credit"
check "conserva la línea comentada" grep -q '^# AUTH_JWT_SIGNING_KEY=comentada' "$dir/.env"
check "no agrega ni quita líneas" equals "$(line_count "$dir/.env")" "$(line_count "$dir/.env.example")"
check "conserva el CRLF del ejemplo" equals "$(crlf_lines "$dir/.env")" "$(crlf_lines "$dir/.env.example")"
check "no deja temporales" equals "$(find "$dir" -name '.env.demo.*' | wc -l | tr -d ' ')" "0"
check "no cambia el .env.example" grep -q '^DJANGO_SECRET_KEY=cambiar' "$dir/.env.example"

before="$(file_hash "$dir/.env")"
check "si ya existe, devuelve 'ya existía'" returns "$DEMO_ENV_EXISTED" demo_ensure_env "$dir"
check "si ya existe, no lo toca" equals "$(file_hash "$dir/.env")" "$before"

dir="$WORK/backend-propio"
make_example "$dir"
printf 'MI_CONFIG=no-tocar\n' >"$dir/.env"
before="$(file_hash "$dir/.env")"
demo_ensure_env "$dir" >/dev/null 2>&1
check "un .env propio queda idéntico" equals "$(file_hash "$dir/.env")" "$before"

dir="$WORK/backend-sin-ejemplo"
mkdir -p "$dir"
check "sin .env.example es un error" returns "$DEMO_EXIT_ERROR" demo_ensure_env "$dir"
check "sin .env.example no crea nada" [ ! -e "$dir/.env" ]

# --- Confirmación del borrado --------------------------------------------------------
confirm_with() { printf '%s' "$1" | demo_confirm_reset >/dev/null; }
check "BORRAR confirma" confirm_with $'BORRAR\n'
check "BORRAR con CRLF confirma" confirm_with $'BORRAR\r\n'
check "borrar en minúsculas no confirma" returns 1 confirm_with $'borrar\n'
check "una respuesta vacía no confirma" returns 1 confirm_with $'\n'
check "sin entrada no confirma" returns 1 confirm_with ""

printf '%s pruebas pasaron, %s fallaron\n' "$PASSED" "$FAILED"
[ "$FAILED" -eq 0 ]
