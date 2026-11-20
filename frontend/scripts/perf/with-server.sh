#!/usr/bin/env bash
# Levanta `next start -p 3003` sobre el build ya hecho, corre measure.mjs con los argumentos
# dados y detiene el servidor, todo en un comando. Uso, desde frontend/:
#   scripts/perf/with-server.sh --out ../../_perf-work/run --roles asesora --pages expediente
set -u
FRONT="$(cd "$(dirname "$0")/../.." && pwd)"
# En Git Bash (Windows), rutas C:/... para node; sin tocar MSYS_NO_PATHCONV, que rompería taskkill.
if command -v cygpath > /dev/null; then FRONT="$(cygpath -m "$FRONT")"; fi
PORT="${PERF_PORT:-3003}"
if ! [ -f "$FRONT/.next/BUILD_ID" ]; then echo "Falta el build: corre 'pnpm build' antes."; exit 1; fi
(cd "$FRONT" && node node_modules/next/dist/bin/next start -p "$PORT" > "${TMPDIR:-/tmp}/perf-next-start.log" 2>&1 &)
for _ in $(seq 1 40); do curl -s -o /dev/null "http://localhost:$PORT/login" && break; sleep 1; done
PERF_BASE_URL="http://localhost:$PORT" node "$FRONT/scripts/perf/measure.mjs" "$@"
code=$?
# Detiene el `next start` del puerto (en Windows queda el proceso hijo escuchando).
if command -v taskkill > /dev/null; then
  pid=$(netstat -ano | grep -E ":$PORT\s" | grep LISTENING | awk '{print $5}' | head -1)
  [ -n "$pid" ] && env -u MSYS_NO_PATHCONV taskkill //PID "$pid" //T //F > /dev/null
else
  pkill -f "next start -p $PORT" || true
fi
exit $code
