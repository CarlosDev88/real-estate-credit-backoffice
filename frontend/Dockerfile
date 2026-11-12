# Frontend de producción (Next.js). Se construye desde la raíz del repo:
#   docker build -f frontend/Dockerfile .
# porque el frontend importa ../design/generated (tokens del design system).

ARG NODE_IMAGE=node:24.22.2-alpine

# 1. Dependencias: solo package.json y el lockfile, para aprovechar la caché de capas.
FROM ${NODE_IMAGE} AS deps
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# 2. Build. Next fija los rewrites de /api/v1 al compilar: API_ORIGIN tiene que estar aquí,
#    no basta con definirla al arrancar.
FROM deps AS build
ARG API_ORIGIN=http://backend:8000
ENV API_ORIGIN=${API_ORIGIN} \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY design/generated ./design/generated
COPY contracts ./contracts
COPY frontend ./frontend
WORKDIR /app/frontend
RUN pnpm build

# 3. Ejecución: usuario sin privilegios y `pnpm start`.
FROM ${NODE_IMAGE} AS run
ARG API_ORIGIN=http://backend:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    API_ORIGIN=${API_ORIGIN}
RUN corepack enable
WORKDIR /app/frontend
COPY --from=build --chown=node:node /app/frontend ./
USER node
# Descarga pnpm (versión de packageManager) al construir, para no necesitar red al arrancar.
RUN pnpm --version
EXPOSE 3000
CMD ["pnpm", "start"]
