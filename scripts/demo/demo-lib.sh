# shellcheck shell=bash
# Las constantes y DEMO_ACTION/DEMO_FULL las usan demo.sh y las pruebas, que cargan este archivo.
# shellcheck disable=SC2034
# Lógica de la demo, separada de Docker para poder probarla sola
# (scripts/demo/test-demo-lib.sh). La usa demo.sh, en la raíz del repo.
#
# Reglas:
# - backend/.env se crea desde backend/.env.example SOLO si no existe; si existe, no se
#   toca nunca (ni se lee para escribir).
# - Las claves nuevas salen de un generador criptográfico y tienen 48 bytes de azar.
# - Los mensajes van en español; los colores, solo si la salida es una terminal.

# Códigos de salida (también los documenta docs/guia/10-operacion-local.md).
DEMO_EXIT_OK=0
DEMO_EXIT_ERROR=1
DEMO_EXIT_USAGE=2
DEMO_EXIT_DOCKER=3
DEMO_EXIT_TIMEOUT=4
DEMO_EXIT_CANCELLED=5

# Variables que la demo escribe al crear backend/.env.
DEMO_SECRET_KEYS=(DJANGO_SECRET_KEY AUTH_JWT_SIGNING_KEY)
DEMO_SECRET_BYTES=48
DEMO_RESET_WORD="BORRAR"

# --- Salida --------------------------------------------------------------------------

demo_color_init() {
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
    DEMO_C_RESET=$'\033[0m'
    DEMO_C_BOLD=$'\033[1m'
    DEMO_C_GREEN=$'\033[32m'
    DEMO_C_YELLOW=$'\033[33m'
    DEMO_C_RED=$'\033[31m'
    DEMO_C_CYAN=$'\033[36m'
  else
    DEMO_C_RESET="" DEMO_C_BOLD="" DEMO_C_GREEN="" DEMO_C_YELLOW="" DEMO_C_RED="" DEMO_C_CYAN=""
  fi
}

demo_step() { printf '%s==>%s %s\n' "${DEMO_C_CYAN}${DEMO_C_BOLD}" "$DEMO_C_RESET" "$*"; }
demo_ok() { printf '%s✓%s %s\n' "$DEMO_C_GREEN" "$DEMO_C_RESET" "$*"; }
demo_warn() { printf '%s!%s %s\n' "$DEMO_C_YELLOW" "$DEMO_C_RESET" "$*" >&2; }
demo_error() { printf '%sError:%s %s\n' "${DEMO_C_RED}${DEMO_C_BOLD}" "$DEMO_C_RESET" "$*" >&2; }

# --- Argumentos ----------------------------------------------------------------------

demo_usage() {
  cat <<'EOF'
Uso: ./demo.sh [--full] [--stop | --reset] [--help]

Sin opciones levanta la demo en el modo simple (postgres, backend y frontend), carga los
datos de demo e imprime las URL y los usuarios.

  --full    Levanta también el perfil "full" (Redis, SeaweedFS, worker y ClamAV).
            Requiere el bloque "Full" activo en backend/.env.
  --stop    Detiene los contenedores sin borrar nada.
  --reset   Borra los contenedores Y los volúmenes (base de datos y documentos).
            Pide escribir BORRAR para confirmar.
  --help    Muestra esta ayuda.
EOF
}

# Deja el resultado en DEMO_ACTION (start | stop | reset | help) y DEMO_FULL (0 | 1).
demo_parse_args() {
  DEMO_ACTION="start"
  DEMO_FULL=0
  local arg
  for arg in "$@"; do
    case "$arg" in
      --full) DEMO_FULL=1 ;;
      --stop)
        if [ "$DEMO_ACTION" = "reset" ]; then demo_error "--stop y --reset no van juntos."; return "$DEMO_EXIT_USAGE"; fi
        DEMO_ACTION="stop" ;;
      --reset)
        if [ "$DEMO_ACTION" = "stop" ]; then demo_error "--stop y --reset no van juntos."; return "$DEMO_EXIT_USAGE"; fi
        DEMO_ACTION="reset" ;;
      -h | --help) DEMO_ACTION="help" ;;
      *) demo_error "Opción desconocida: $arg"; return "$DEMO_EXIT_USAGE" ;;
    esac
  done
  return "$DEMO_EXIT_OK"
}

# --- Secretos y backend/.env ---------------------------------------------------------

# Un secreto válido: base64 de URL de al menos 64 caracteres (48 bytes).
demo_secret_ok() {
  [[ "$1" =~ ^[A-Za-z0-9_-]{64,}$ ]]
}

# Imprime un secreto aleatorio de DEMO_SECRET_BYTES bytes en base64 de URL (sin "=").
# Prueba, en orden: el módulo `secrets` de Python, /dev/urandom y openssl. Cada salida se
# valida, para que un "python" falso (el atajo de la tienda de Windows) no cuele basura.
demo_generate_secret() {
  local secret="" py
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      secret="$("$py" -c "import secrets; print(secrets.token_urlsafe($DEMO_SECRET_BYTES))" 2>/dev/null | tr -d '\r\n')" || secret=""
      demo_secret_ok "$secret" && break
      secret=""
    fi
  done
  if [ -z "$secret" ] && [ -r /dev/urandom ]; then
    secret="$(head -c "$DEMO_SECRET_BYTES" /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n\r')"
    demo_secret_ok "$secret" || secret=""
  fi
  if [ -z "$secret" ] && command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -base64 "$DEMO_SECRET_BYTES" | tr '+/' '-_' | tr -d '=\n\r')"
    demo_secret_ok "$secret" || secret=""
  fi
  if [ -z "$secret" ]; then
    demo_error "No hay un generador de números aleatorios seguro (python3, /dev/urandom u openssl)."
    return "$DEMO_EXIT_ERROR"
  fi
  printf '%s\n' "$secret"
}

# demo_set_env_value ARCHIVO CLAVE VALOR
# Reemplaza la primera línea "CLAVE=..." (sin comentar) o la agrega al final. Conserva el
# fin de línea del archivo (LF o CRLF). El valor no debe tener espacios ni comillas.
# En bash puro y no con awk: el awk de Git Bash en Windows quita los CR al leer.
demo_set_env_value() {
  local file="$1" key="$2" value="$3" tmp line cr eol=$'\n' done=0
  tmp="$(mktemp "${file}.XXXXXX")" || return "$DEMO_EXIT_ERROR"
  while IFS= read -r line || [ -n "$line" ]; do
    cr=""
    if [ "${line%$'\r'}" != "$line" ]; then
      cr=$'\r'
      eol=$'\r\n'
      line="${line%$'\r'}"
    fi
    if [ "$done" -eq 0 ] && [ "${line#"$key="}" != "$line" ]; then
      printf '%s=%s%s\n' "$key" "$value" "$cr"
      done=1
    else
      printf '%s%s\n' "$line" "$cr"
    fi
  done <"$file" >"$tmp" || { rm -f "$tmp"; return "$DEMO_EXIT_ERROR"; }
  if [ "$done" -eq 0 ]; then
    printf '%s=%s%s' "$key" "$value" "$eol" >>"$tmp"
  fi
  mv "$tmp" "$file"
}

# demo_get_env_value ARCHIVO CLAVE [POR_OMISIÓN]
demo_get_env_value() {
  local file="$1" key="$2" default="${3:-}" value="" line
  if [ -f "$file" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%$'\r'}"
      if [ "${line#"$key="}" != "$line" ]; then
        value="${line#"$key="}"
        break
      fi
    done <"$file"
  fi
  if [ -n "$value" ]; then printf '%s\n' "$value"; else printf '%s\n' "$default"; fi
}

# demo_ensure_env DIRECTORIO_DEL_BACKEND
# Devuelve 0 si creó backend/.env, 10 si ya existía (y no lo tocó) u otro código si falló.
DEMO_ENV_EXISTED=10
demo_ensure_env() {
  local dir="$1" env_file="$1/.env" example="$1/.env.example" tmp key secret
  if [ -e "$env_file" ]; then
    return "$DEMO_ENV_EXISTED"
  fi
  if [ ! -f "$example" ]; then
    demo_error "No existe $example: no hay de dónde crear backend/.env."
    return "$DEMO_EXIT_ERROR"
  fi
  tmp="$(mktemp "${dir}/.env.demo.XXXXXX")" || return "$DEMO_EXIT_ERROR"
  if ! cp "$example" "$tmp"; then
    rm -f "$tmp"
    return "$DEMO_EXIT_ERROR"
  fi
  for key in "${DEMO_SECRET_KEYS[@]}"; do
    if ! secret="$(demo_generate_secret)"; then
      rm -f "$tmp"
      return "$DEMO_EXIT_ERROR"
    fi
    demo_set_env_value "$tmp" "$key" "$secret" || { rm -f "$tmp"; return "$DEMO_EXIT_ERROR"; }
  done
  demo_set_env_value "$tmp" "DJANGO_DEBUG" "True" || { rm -f "$tmp"; return "$DEMO_EXIT_ERROR"; }
  chmod 600 "$tmp" 2>/dev/null || true
  # `mv -n` no pisa un .env que haya aparecido mientras tanto.
  if ! mv -n "$tmp" "$env_file" || [ -e "$tmp" ]; then
    rm -f "$tmp"
    return "$DEMO_ENV_EXISTED"
  fi
  return "$DEMO_EXIT_OK"
}

# --- Espera y confirmación -----------------------------------------------------------

# demo_wait_url URL SEGUNDOS [INTERVALO]: espera un 2xx. Devuelve 0 o DEMO_EXIT_TIMEOUT.
demo_wait_url() {
  local url="$1" timeout="$2" interval="${3:-3}" start now
  start="$(date +%s)"
  while :; do
    if curl --silent --fail --max-time 5 --output /dev/null "$url"; then
      return "$DEMO_EXIT_OK"
    fi
    now="$(date +%s)"
    if [ $((now - start)) -ge "$timeout" ]; then
      return "$DEMO_EXIT_TIMEOUT"
    fi
    sleep "$interval"
  done
}

# demo_confirm_reset: lee una línea de la entrada y acepta solo DEMO_RESET_WORD exacto.
demo_confirm_reset() {
  local answer=""
  printf 'Esto borra la base de datos y los documentos de la demo. Escribe %s para confirmar: ' "$DEMO_RESET_WORD"
  IFS= read -r answer || answer=""
  answer="${answer%$'\r'}"
  [ "$answer" = "$DEMO_RESET_WORD" ]
}
