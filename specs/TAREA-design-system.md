# Tarea: design system Umbral en Storybook y librería de componentes

## Objetivo
Convertir lo que ya existe (los tokens de Umbral y los componentes de F0, F1, F2 y F3) en **una librería documentada en Storybook**, para que las ~14 vistas que faltan se construyan encima de ella y no haya que corregirlas después. **Carlos es quien revisa este trabajo:** Storybook es el entregable que él va a mirar.

## Cuándo y dónde
- **Agente:** front 1, cuando termine la F2 (portal), en un worktree nuevo `wt-front-ds`, rama `feat/design-system`, desde `master` (con F2 y F3 fusionadas o, al menos, F2).
- **En paralelo:** el front 2 construye vistas nuevas (clientes) en `wt-front-clients`.
- **Propiedad:** desde ahora, **tú eres el dueño de `frontend/src/components/ui/`** y de los tokens que consume el front. El front 2 no crea componentes compartidos: crea los suyos dentro de su feature, y tú decides si pasan a la librería.

## Reglas de trabajo
- Git solo en lectura. Carlos hace todos los commits y push, sin `Co-Authored-By` ni firmas.
- **Comunicación por buzón:** reporte completo, `ESTADO.md` al día y en la consola una línea.
- **No se presentan dudas.** Lo que no esté cubierto lo decides tú con la opción más simple y coherente con `design/README.md`, lo anotas en "Precisiones acordadas" y sigues.
- **No se cambia el aspecto aprobado** (mockups y tokens) sin anotarlo. Corregir para acercarse al mockup sí se puede.
- **Versiones:** la última estable de Storybook compatible con Next 16, React 19 y Vite 8, con la regla de antigüedad mínima de pnpm de F0 (si la versión es muy nueva, la anterior). Framework `@storybook/nextjs-vite`. Verifica la compatibilidad antes de instalar y anótala.
- Verificaciones al cerrar cada parte: `lint`, `format:check`, `typecheck`, tests con cobertura ≥ 70 %, `build` y `build-storybook`.

## Parte 1. Storybook y fundamentos
- **Instalación:** Storybook en `frontend/`, con `storybook` y `build-storybook` en `package.json`. Los stories viven junto a cada componente (`*.stories.tsx`) y los documentos en `frontend/src/stories/`.
- **Decorador global:**
  - providers reales (`AntdRegistry` con `layer`, `ConfigProvider` con `lightTheme`/`darkTheme` y Query);
  - las fuentes;
  - un **selector de tema** claro/oscuro en la barra de Storybook que aplica `data-theme` y el tema de Ant Design juntos, igual que la app.
- **Addons:**
  - accesibilidad (`@storybook/addon-a11y`, falla con violaciones serias o críticas);
  - viewports 390, 1280 y 1440;
  - docs (MDX y autodocs).
- **Páginas de fundamentos (MDX)**, leyendo los archivos generados de `design/generated/` sin copiar valores:
  - colores con sus nombres de token, en claro y oscuro;
  - tipografía (familias, pesos y escala);
  - espaciado;
  - radios;
  - sombras y elevación (con la regla "no sombras en el flujo");
  - tonos de estado (`status-tones.ts`) con la regla "el estado nunca solo por color";
  - las reglas de redacción del README (frases en *sentence case*, enlaces subrayados, etc.).
- **CI:** agrega `build-storybook` al workflow del front como una fila nueva, "Storybook", en el reporte del PR (extiende `scripts/ci-report.ts` y sus pruebas). Falla si no compila.

**Commit:** `feat(ui): add Storybook with the Umbral foundations, themes and a11y checks`

## Parte 2. Librería de componentes
- **Un story por cada componente de `components/ui`**, con sus estados: vacío, cargando, error, deshabilitado, largo y en móvil, en claro y oscuro, y con `argTypes` documentados. Incluye:
  - `AppShell`, `ThemeToggle`, `StatusBadge`, `Money`, `MoneyInput`, `CompletenessBar`, `ScrollTabs`, `FilterChips`, `EmptyState`, `DocumentViewer`, `DocumentUploader` y `RelativeTime`;
  - toasts;
  - todo lo que se haya sumado en F1, F2 y F3.
- **Auditoría de duplicados** en `features/` (F1 backoffice, F2 portal, F3 radicación): piezas casi iguales que deberían ser una (stepper, tarjetas de resumen, filas de documento, modales de acción, paneles laterales, formularios de campo con error, estados vacíos y de error, encabezados de página).
  - Las que se repiten en dos o más features **pasan a `components/ui`**, con su story y sus pruebas, y se reemplazan en las features.
  - Cada reemplazo, con sus pruebas en verde.
- **Mejoras pendientes de F1** (anotadas en su reporte):
  - `CompletenessBar` con el total en el encabezado y datos y documentos lado a lado, como el mockup;
  - `ScrollTabs` con conteo en tono de advertencia ("6 pendientes").

  Se hacen sin romper a quien ya los usa.
- **Patrones (MDX con ejemplos vivos):**
  - formulario con validación y error de la API;
  - lista con filtros en la URL;
  - tabla con orden y paginación, más su versión en tarjetas en móvil;
  - panel lateral de revisión;
  - modal de confirmación de acción (incluida la destructiva);
  - carga de archivo;
  - estados vacío, cargando y error;
  - encabezado de página con migas y acciones.

**Commit:** `feat(ui): document the component library in Storybook and promote shared patterns`

## Parte 3. Auditoría de consistencia y reglas de uso
- **Revisión de todas las pantallas existentes** (backoffice y portal) contra los tokens:
  - colores, espaciados o tamaños de letra escritos a mano en lugar de tokens o clases del tema;
  - componentes de Ant Design usados sin el tema;
  - contrastes;
  - foco visible;
  - tamaños táctiles en móvil.

  Corrige lo que encuentres y lista cada hallazgo en el reporte.
- **Regla automática:** una regla de ESLint, o una prueba, que falle si aparece un color hexadecimal o `rgb()` en `src/` fuera de los archivos permitidos.
- **Guía de uso** (`frontend/src/stories/guia.mdx`):
  - cuándo usar cada componente;
  - qué no hacer;
  - cómo crear un componente nuevo (dónde va, story, pruebas y accesibilidad);
  - cómo pedir uno desde una feature.
- **Capturas de Storybook** (fundamentos y 5 componentes clave), en claro y oscuro, en `frontend/test-results/`.
- **Trae `master` antes de entregar.** Entregas el **título y la descripción del PR**, en español, sin firmas, con el comando para abrir Storybook en local.

**Commit:** `chore(ui): audit token usage across screens and add the component usage guide`

## Precisiones acordadas

**Parte 1 (Storybook y fundamentos):**
- **Versiones:** Storybook 10.6.7 (`storybook`, `@storybook/nextjs-vite`, `@storybook/addon-docs`, `@storybook/addon-a11y`, `@storybook/addon-vitest` y `eslint-plugin-storybook`). Es la última estable (`latest`), publicada el 2026-11-10, fuera de la antigüedad mínima de pnpm. `@storybook/nextjs-vite` 10.6.7 declara `next ^16`, `vite ^8` y `react ^19`. La 11 sigue en beta. Para correr los stories en el navegador: `@vitest/browser` y `@vitest/browser-playwright` 5.1.0 (iguales a vitest) y `playwright` 1.65.0 (igual a `@playwright/test`, así se reusa el Chromium que ya está instalado).
- **esbuild:** llega con Storybook, y pnpm 12 frena la instalación si un paquete tiene un script de build sin aprobar. `frontend/pnpm-workspace.yaml` (solo ajustes, no es un monorepo) declara `allowBuilds: esbuild: false`: el binario viene en el paquete opcional de cada plataforma y no hace falta su script. El Dockerfile copia ese archivo junto al lockfile.
- **a11y que falla:** `parameters.a11y.test = "error"` con `options.impactLevels = ["serious", "critical"]`. Falla en `pnpm test:storybook` (addon de Vitest, Chromium sin ventana), que corre cada story como una prueba. Las violaciones leves y moderadas se ven en el panel, pero no hacen fallar. Se probó con stories temporales: `button-name` (crítica) y `color-contrast` en oscuro (seria) fallan; `heading-order` (moderada) pasa.
- **CI:** la fila "Storybook" solo compila (`pnpm build-storybook`), como dice la spec. `test:storybook` no corre en el CI porque necesitaría instalar Chromium en el runner. **Pendiente:** sumarlo en la parte 3 si Carlos lo quiere.
- **`design/README.md` en el CI:** la página de tonos lee del README el uso de cada tono. Por eso, un cambio en el README también activa el workflow del front.
- **Tema:** el selector "Tema" de la barra es el global `theme`. El decorador aplica `data-theme` antes de pintar y remonta el `ThemeProvider` real con ese modo, así que Ant Design y los tokens cambian juntos. Si un story cambia el tema por su cuenta (el `ThemeToggle`), la barra lo sigue. Las páginas MDX siguen el mismo global con un contenedor de docs, cuyos colores vienen de `antd-theme.ts`. Para una captura, se abre con `&globals=theme:dark`.
- **Providers:** los mismos de `app/layout.tsx`: `AntdRegistry` con `layer`, `ThemeProvider`, `AntdProvider` (con `App` y los toasts) y `QueryProvider`. Se importan los mismos `@fontsource` y `globals.css`.
- **Fundamentos sin copiar valores:** `src/stories/fundamentos/tokens.ts` lee como texto (`?raw`) `tokens.css`, `tailwind-theme.css`, `status-tones.ts` y la tabla "Estados" de `design/README.md`. Las páginas pintan con `var(--um-*)` y muestran el valor leído. El reporte de contraste se muestra tal cual desde `contrast-report.md`. El nombre del token se deriva de la variable CSS (`brand-primary-hover` → `brand.primaryHover`), con prueba. Para eso, Vitest permite leer `../design` y procesa esos dos CSS (por defecto los vacía).
- **Stories de los fundamentos:** las páginas MDX muestran los bloques con `<Story of>` desde `fundamentos.stories.tsx` (`Fundamentos/Bloques`, con la etiqueta `!dev`: no sale en la barra lateral). Así tienen los providers reales y pasan por la revisión de a11y. El ejemplo "Así no" de enlaces sin subrayar desactiva solo la regla `link-in-text-block` en su story.
- **Cobertura:** los `*.stories.tsx` quedan fuera de la cobertura de `pnpm test` (corren en `test:storybook`). Los bloques y el lector de tokens sí tienen pruebas en jsdom.
- **Tablas en MDX:** el MDX de Storybook no trae GFM. Las dos tablas propias van en JSX, en lugar de sumar `remark-gfm`.
- **Manager:** se ve "Umbral · Design system", sin la lista "Get started" ni los avisos de versiones nuevas, y sin telemetría.
- **Viewports:** Móvil 390×844, Portátil 1280×800 y Escritorio 1440×900. El alto lo elegí yo.
- **Redacción:** además del README, se usa el tuteo de los mockups ("Sube…", "Puedes reemplazarlo…").
