#!/usr/bin/env bash
# Demo con un solo comando (Linux y macOS; en Windows también corre con Git Bash).
#
#   ./demo.sh            levanta el modo simple, carga los datos de demo e imprime el acceso
#   ./demo.sh --full     lo mismo con el perfil "full" (Redis, SeaweedFS, worker, ClamAV)
#   ./demo.sh --stop     detiene los contenedores sin borrar nada
#   ./demo.sh --reset    borra contenedores y volúmenes (pide escribir BORRAR)
#
# Guía: docs/guia/10-operacion-local.md. La lógica que no necesita Docker vive en
# scripts/demo/demo-lib.sh y se prueba con scripts/demo/test-demo-lib.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
# shellcheck source=scripts/demo/demo-lib.sh
. "$ROOT_DIR/scripts/demo/demo-lib.sh"

demo_color_init
rc=0
demo_parse_args "$@" || rc=$?
if [ "$rc" -ne 0 ]; then
  demo_usage >&2
  exit "$rc"
fi
if [ "$DEMO_ACTION" = "help" ]; then
  demo_usage
  exit "$DEMO_EXIT_OK"
fi

# Todas las llamadas a compose corren desde backend/, donde están el compose y el .env.
compose() {
  (cd "$BACKEND_DIR" && docker compose "$@")
}

# --- 1. Docker -----------------------------------------------------------------------
demo_step "Revisando Docker"
if ! command -v docker >/dev/null 2>&1; then
  demo_error "No encuentro el comando docker. Instala Docker Desktop (o Docker Engine con el plugin compose)."
  exit "$DEMO_EXIT_DOCKER"
fi
if ! docker info >/dev/null 2>&1; then
  demo_error "Docker no está corriendo. Ábrelo (Docker Desktop) y vuelve a intentarlo."
  exit "$DEMO_EXIT_DOCKER"
fi
if ! docker compose version >/dev/null 2>&1; then
  demo_error "Falta Docker Compose v2 (el comando 'docker compose')."
  exit "$DEMO_EXIT_DOCKER"
fi
demo_ok "Docker responde"

# --- Detener o borrar ----------------------------------------------------------------
if [ "$DEMO_ACTION" = "stop" ]; then
  demo_step "Deteniendo los contenedores (los datos se conservan)"
  compose --profile full stop
  demo_ok "Demo detenida. Vuelve a levantarla con ./demo.sh"
  exit "$DEMO_EXIT_OK"
fi

if [ "$DEMO_ACTION" = "reset" ]; then
  if [ ! -t 0 ]; then
    demo_error "Borrar los datos exige confirmarlo en una terminal interactiva."
    exit "$DEMO_EXIT_CANCELLED"
  fi
  if ! demo_confirm_reset; then
    demo_warn "No se borró nada."
    exit "$DEMO_EXIT_CANCELLED"
  fi
  demo_step "Borrando contenedores y volúmenes"
  compose --profile full down --volumes --remove-orphans
  demo_ok "Listo. backend/.env no se tocó. Vuelve a empezar con ./demo.sh"
  exit "$DEMO_EXIT_OK"
fi

# --- 2. backend/.env -----------------------------------------------------------------
demo_step "Revisando backend/.env"
rc=0
demo_ensure_env "$BACKEND_DIR" || rc=$?
case "$rc" in
  "$DEMO_EXIT_OK") demo_ok "Creé backend/.env desde .env.example, con claves nuevas (DJANGO_SECRET_KEY y AUTH_JWT_SIGNING_KEY) y DJANGO_DEBUG=True" ;;
  "$DEMO_ENV_EXISTED") demo_ok "backend/.env ya existe: no lo toco" ;;
  *) exit "$DEMO_EXIT_ERROR" ;;
esac

ENV_FILE="$BACKEND_DIR/.env"
BACKEND_PORT="${BACKEND_HOST_PORT:-$(demo_get_env_value "$ENV_FILE" BACKEND_HOST_PORT 8000)}"
FRONTEND_PORT="${FRONTEND_HOST_PORT:-$(demo_get_env_value "$ENV_FILE" FRONTEND_HOST_PORT 3000)}"
API_URL="http://localhost:${BACKEND_PORT}"
WEB_URL="http://localhost:${FRONTEND_PORT}"

# --- 3. Contenedores -----------------------------------------------------------------
PROFILE_ARGS=()
TIMEOUT="${DEMO_TIMEOUT_SECONDS:-300}"
if [ "$DEMO_FULL" -eq 1 ]; then
  PROFILE_ARGS=(--profile full)
  TIMEOUT="${DEMO_TIMEOUT_SECONDS:-600}"
  demo_warn "Modo completo: el backend usa Redis, SeaweedFS y ClamAV solo si backend/.env tiene activo el bloque \"Full\". ClamAV tarda varios minutos en bajar sus firmas la primera vez."
  demo_step "Levantando la demo en el modo completo (la primera vez construye las imágenes)"
else
  demo_step "Levantando la demo en el modo simple: postgres, backend y frontend (la primera vez construye las imágenes)"
fi
# La forma ${arr[@]+...} evita el error de "variable sin definir" de bash 3.2 (macOS)
# con un arreglo vacío y `set -u`.
compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} up -d --build

# --- 4. Salud ------------------------------------------------------------------------
demo_step "Esperando a la API (hasta ${TIMEOUT} s): migraciones y arranque"
for probe in health ready; do
  if ! demo_wait_url "${API_URL}/${probe}" "$TIMEOUT"; then
    demo_error "La API no respondió en ${API_URL}/${probe} después de ${TIMEOUT} s."
    demo_error "Mira qué pasó con: (cd backend && docker compose logs --tail 80 backend)"
    exit "$DEMO_EXIT_TIMEOUT"
  fi
done
demo_ok "API lista en ${API_URL}"

# --- 5. Datos de demo ----------------------------------------------------------------
demo_step "Cargando los datos de demo (se puede repetir: agrega solo lo que falta y nunca borra)"
echo
# --new-portal-link: cada corrida imprime un enlace del portal (revoca el anterior sin usar).
if ! compose exec -T backend python manage.py seed_demo_data --new-portal-link; then
  demo_error "Falló la carga de datos de demo. Revisa el mensaje de arriba."
  exit "$DEMO_EXIT_ERROR"
fi
echo

# --- 6. Resumen ----------------------------------------------------------------------
if ! demo_wait_url "${WEB_URL}/login" 120; then
  demo_warn "El frontend todavía no responde en ${WEB_URL}. Revisa: (cd backend && docker compose logs --tail 80 frontend)"
fi

printf '%s\n' "${DEMO_C_BOLD}Demo lista${DEMO_C_RESET}"
printf '  Backoffice ................ %s\n' "${WEB_URL}/login"
printf '  Portal del comprador ...... el enlace de un solo uso que imprimió el seed, arriba (72 horas)\n'
printf '  API ....................... %s\n' "${API_URL}/api/v1/"
printf '  Documentación de la API ... %s (solo con DEBUG)\n' "${API_URL}/docs"
printf '  Usuarios y contraseña ..... en la tabla que imprimió el seed, arriba\n'
echo
printf '  Detener sin borrar ........ ./demo.sh --stop\n'
printf '  Empezar de cero ........... ./demo.sh --reset\n'
printf '  Recorrido sugerido ........ docs/guia/10-operacion-local.md\n'
exit "$DEMO_EXIT_OK"
