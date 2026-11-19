# ADR 0013 · Design system propio en Storybook, con accesibilidad en el CI

- **Estado:** aceptada.
- **Fecha:** tokens (#9, #10) y design system en Storybook (#28); registrada el 2026-11-18.
- **Fuentes:** `design/README.md`, `design/tokens/tokens.json`, `design/generated/`; [`specs/TAREA-design-system.md`](../../specs/TAREA-design-system.md); `frontend/.storybook/preview.tsx`; `frontend/src/test/no-hardcoded-colors.test.ts`; `.github/workflows/frontend.yml` (pasos "Storybook" y "Storybook (a11y)"); [08 · Frontend §3](../guia/08-frontend.md#3-design-system-y-componentsui).

## Contexto

Las 22 vistas las construyen agentes distintos en momentos distintos. Sin una fuente común, cada pantalla termina con sus propios colores, tamaños y patrones, y la accesibilidad depende de que cada uno se acuerde.

## Opciones consideradas

1. **Usar Ant Design tal cual**, sin capa propia. Rápido, pero los estados del negocio, los tonos y los patrones del portal no existen ahí.
2. **Una guía de estilo en un documento.** Nadie la verifica.
3. **Design system propio (Umbral)**: tokens como fuente única que generan CSS, el tema de Ant Design, el tema de Tailwind y los tonos de estado; componentes compartidos documentados en Storybook; y reglas verificadas por el CI.

## Decisión

Opción 3. Los tokens viven en `design/tokens/tokens.json` y un script genera `tokens.css`, `tailwind-theme.css`, `antd-theme.ts`, `status-tones.ts` y un reporte de contraste; el frontend los **importa**, nunca los copia. Los componentes compartidos están en `frontend/src/components/ui` y se documentan en **Storybook 10** con stories y páginas MDX de fundamentos y patrones. En el CI: Storybook debe compilar, y **cada story pasa `axe`** en Chromium (falla con violaciones serias o críticas). Una prueba falla si aparece un color escrito a mano en `frontend/src/`. El color de un estado sale siempre de `toneFor(kind, code)` y su texto, de la API.

## Consecuencias

- **A favor:** la consistencia se comprueba sola; la auditoría de consistencia (Parte 3 de la spec) pudo migrar las pantallas existentes y dejar la regla en el CI; un problema de contraste se ve en el PR, no en producción (pasó con un estado de carga al 60 % de opacidad).
- **En contra:** el job del front tardó más (de 15 a 20 minutos de límite) por instalar Chromium y correr las stories; algunas excepciones se justifican a mano (por ejemplo, el papel blanco del visor de documentos).
- **Publicado** (F7, #33): el Storybook está en GitHub Pages, <https://carlosdev88.github.io/real-estate-credit-backoffice/>, con la referencia de la API en `/api/`; lo publica `.github/workflows/storybook-pages.yml` en cada push a `master` que toque el frontend, el diseño o el contrato. El documento del design system es [`docs/DESIGN-SYSTEM.md`](../DESIGN-SYSTEM.md).
