# Medición de performance en local

Con estos scripts se repite la medición de la auditoría de performance del front (`docs/PERFORMANCE.md`). Sirven sobre todo para las páginas con sesión, que no van al CI porque necesitan backend y datos. Las públicas sí corren en el CI con Lighthouse CI (`lighthouserc.json`).

## Preparar

1. **Backend** en `:8000` con la demo (`backend/README.md`, "Demo Data"). El backend tiene que aceptar el origen `http://localhost:3003`.
2. **Herramientas fuera del repo.** Solo sirven para medir, por eso no están en `package.json`. Por omisión van en `../../_perf-tools`, al lado del repo; con `PERF_TOOLS` se elige otra carpeta:
   ```bash
   npm install --prefix ../../_perf-tools lighthouse@13.6.0 web-vitals@6.2.3
   ```
   Playwright es el del repo (`pnpm exec playwright install chromium`).
3. **Build de producción limpio.** Con un `.next` reusado tras muchos builds, los números salen distintos:
   ```bash
   rm -rf .next && pnpm build
   ```

## Medir

Desde `frontend/`. El wrapper levanta `next start -p 3003`, mide y lo detiene:

```bash
# Las 13 páginas de la auditoría (unos 75 min). Hace 3 logins y crea 1 enlace de comprador.
scripts/perf/with-server.sh --out ../../_perf-work/campana/run-todo

# Una página o un perfil
scripts/perf/with-server.sh --out ../../_perf-work/campana/run-exp --roles asesora --pages expediente \
  --profiles mobile,desktop,vitals
scripts/perf/with-server.sh --out ../../_perf-work/campana/run-inp --roles asesora --pages interacciones --only vitals

# Tablas Markdown (medianas de 5). Con una segunda carpeta, el antes → después.
node scripts/perf/report.mjs ../../_perf-work/campana [../../_perf-work/linea-base]
```

- **Opciones:**
  - `--roles`: `public`, `admin`, `asesora`, `broker`, `buyer`. El comprador necesita también `asesora`, que crea su enlace.
  - `--pages`: los ids de `config.mjs`, más `interacciones`.
  - `--profiles`: Lighthouse `mobile`, `desktop` y `warm` (caché tibia), y Web Vitals `vitals` y `vitals-warm`.
- **Salida:** `results.json`, con las corridas, las medianas y la red, y los JSON y HTML de Lighthouse en `<out>/lighthouse/<perfil>/`. `report.mjs` junta las carpetas `run-*` de la campaña (una por grupo de páginas).
- **Límite de login:** `5/15m` por correo. Cada corrida hace un login por rol; junta las páginas en pocas corridas.

## Bundle

El JS de primera carga por ruta (gzip) lo revisa el CI contra `performance-budget.json`:

```bash
node scripts/check-bundle-budget.ts            # compara (necesita `pnpm build`)
node scripts/check-bundle-budget.ts --update   # reescribe: lo medido + 10 %, redondeado a 5 kB
```
