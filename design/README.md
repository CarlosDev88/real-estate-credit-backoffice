# Umbral · Design System

Design system del backoffice y del portal del comprador. **Umbral** es el nombre de trabajo del producto: el umbral es la puerta de la casa nueva.

Vista previa: abre `design/preview/index.html` en el navegador. Tiene un botón para cambiar entre tema claro y oscuro.

Pantallas de referencia (mockups aprobados): `design/screens/*.html`. Se abren directo en el navegador y funcionan sin servidor.

| Mockup | Ruta en Next.js | Qué cubre |
| --- | --- | --- |
| `login.html` | `/login` | Login interno, errores y bloqueo por intentos. |
| `solicitudes.html` | `/solicitudes` | Pestañas por estado, búsqueda, filtros (banco, tipo de crédito, finalidad, asesor), chips, selección masiva, tabla ordenable y tarjetas en móvil. |
| `solicitud.html` | `/solicitudes/[id]` | Espacio de trabajo: resumen, completitud, reglas del banco, participantes, documentos con revisión, visor y toasts. |
| `portal.html` | `/portal` | Inicio del comprador en móvil: estado, siguiente paso y progreso. |
| `portal-documentos.html` | `/portal/documentos` | Documentos del comprador (web y móvil): carga, reemplazo, versiones, rechazo con motivo y visor. |

Los mockups son referencia visual y de comportamiento. Los datos y las listas que muestran son de ejemplo: en la app real todo llega de la API.

## Principios

1. **Confianza antes que decoración.** Es un producto de crédito: azul sobrio, mucho espacio en blanco y jerarquía por bordes y fondos, no por sombras ni colores fuertes.
2. **Densidad legible.** El backoffice se usa muchas horas y gira alrededor de tablas. Base de 14 px, controles de 32 px y cifras tabulares en montos y porcentajes.
3. **El estado se ve de un vistazo.** Seis tonos cubren todos los estados de solicitud, documento, archivo y regla.
4. **Accesible por defecto.** Todo par de texto y fondo se verifica contra WCAG 2.1 al generar los tokens. Si uno no cumple, el build falla.
5. **El portal del comprador es móvil primero.** Mismos tokens, controles grandes (40 px) y una sola columna.

## Estructura

| Ruta | Qué es | ¿Se edita? |
| --- | --- | --- |
| `tokens/tokens.json` | Fuente única: paletas, tokens semánticos claro/oscuro, tipografía, espaciado, radios, tonos de estado y pares de contraste a verificar. | **Sí** |
| `scripts/build-tokens.mjs` | Genera todo lo de `generated/` y la vista previa. Node 18+, sin dependencias. | Sí |
| `generated/tokens.css` | Variables CSS `--um-*`, con tema claro (por defecto) y oscuro (`[data-theme="dark"]`). | No |
| `generated/tailwind-theme.css` | Tema de Tailwind v4 (`@theme inline`) que apunta a las variables. | No |
| `generated/antd-theme.ts` | `lightTheme` y `darkTheme` para el `ConfigProvider` de Ant Design. | No |
| `generated/status-tones.ts` | Tono por código de estado y `toneFor(kind, code)`. | No |
| `generated/contrast-report.md` | Resultado de la verificación de contraste. | No |
| `preview/template.html` | Plantilla de la vista previa. | Sí |
| `preview/index.html` | Vista previa con los tokens incrustados. | No |
| `screens/src/*.html` | Fuente de los mockups. Los archivos que empiezan por `_` son piezas compartidas (estilos, menú, visor, toasts). | Sí |
| `screens/*.html` | Mockups generados con los tokens y las piezas incrustadas. | No |

Después de cambiar `tokens.json`, la plantilla o las pantallas de `screens/src/`:

```
node design/scripts/build-tokens.mjs
```

## Uso en el frontend (Next.js)

Stack previsto: Next.js (App Router), Ant Design para componentes y Tailwind CSS v4 para layout y utilidades.

**Estilos globales** (`app/globals.css`):

```css
@layer theme, base, antd, components, utilities;
@import "tailwindcss";
@import "../../design/generated/tokens.css";
@import "../../design/generated/tailwind-theme.css";
```

**Ant Design** (`app/providers.tsx`):

```tsx
import { ConfigProvider } from "antd";
import { StyleProvider } from "@ant-design/cssinjs";
import { lightTheme, darkTheme } from "../../design/generated/antd-theme";

<StyleProvider layer>
  <ConfigProvider theme={isDark ? darkTheme : lightTheme}>{children}</ConfigProvider>
</StyleProvider>;
```

`StyleProvider layer` mete los estilos de Ant Design en una capa CSS, para que el preflight de Tailwind no los pise. Hay solo dos temas: claro (por defecto) y oscuro. No se sigue el tema del sistema operativo; el usuario elige con el botón de la barra superior y la elección se guarda en su navegador. El oscuro se activa con `data-theme="dark"` en `<html>` y con `darkTheme` en el `ConfigProvider`: los dos tienen que ir juntos.

**Reglas:**

- Los componentes usan **tokens semánticos** (`bg-surface`, `text-text-secondary`, `border-border-default`), nunca las paletas (`blue-600`) ni colores escritos a mano.
- Formularios, tablas, selects, modales, menús y notificaciones son componentes de Ant Design. Tailwind se usa para layout, espaciado y casos puntuales.
- Montos y porcentajes con `font-variant-numeric: tabular-nums` (`tabular-nums` en Tailwind). Los montos se formatean en COP con `Intl.NumberFormat("es-CO")`.
- Los códigos (`SOL-000184`) van en fuente mono.

## Estados

`status-tones.ts` asigna un tono visual a cada código de estado:

| Tono | Uso |
| --- | --- |
| `neutral` | Borrador, pendiente, cerrado sin resultado (desistida, cancelada, recursos propios, crédito externo). |
| `info` | En proceso del lado de operación o del banco (revisión documental, radicada, análisis de crédito, documento cargado). |
| `accent` | Avanza bien y requiere una acción del asesor: lista para radicar, documento exonerado. |
| `success` | Resultado positivo: aprobada, en legalización, desembolsada, documento aprobado, archivo limpio. |
| `warning` | Falta algo del comprador o del sistema: esperando datos o documentos, archivo en análisis, datos faltantes en una regla. |
| `danger` | Resultado negativo o riesgo: rechazada, documento rechazado, archivo infectado, regla incumplida. |

**Esto es presentación, no lógica de negocio.** REQUERIMIENTOS §8.5 prohíbe que el frontend defina estados, listas o transiciones. El mapa solo decide el color de una etiqueta que llega del backend: el texto siempre viene de la API (`label`), y un código desconocido cae en `neutral`, así que un estado nuevo nunca rompe la interfaz. **Pendiente:** si se quiere eliminar este mapa, el backend puede exponer el tono en `/metadata`.

## Componentes base

| Componente | En código | Notas |
| --- | --- | --- |
| Botón | `Button` de Ant Design | Primario: una sola acción principal por vista. `danger` solo para acciones destructivas (rechazar, revocar). |
| Campo de texto y monto | `Input`, `InputNumber` | Monto con prefijo `COP`, alineado a la derecha y con separador de miles. |
| Select | `Select` | Las opciones siempre vienen de la API (catálogos). |
| Badge de estado | `Tag` con las clases de tono | Punto de color + etiqueta de la API. Es la única píldora con color: los conteos de pestañas y menús van como texto tabular, sin fondo. |
| Alerta | `Alert` | Mensajes de reglas bancarias: `warning` para datos faltantes y `error` para bloqueos. |
| Tabla | `Table` + TanStack Table para el estado (orden, filtros, selección) | Encabezado en minúscula inicial, 12 px, peso medio y `text.secondary`. Filas de 52 px cuando la celda tiene dos líneas (44 px si es de una), y hover en `brand.subtle`. El orden se activa con un botón dentro del encabezado, para que funcione con teclado; la flecha solo aparece en la columna ordenada. Los filtros visibles no se repiten como chips: los chips son solo para filtros que no se ven en la barra. En móvil, los filtros van en una hoja inferior detrás de un botón "Filtros (n)". |
| Progreso | `Progress` | Completitud: total, datos y documentos por separado. |
| Slot de documento | Componente propio | Estado, archivo vigente, vencimiento y motivo de rechazo visible para el comprador. |
| Layout | `Layout` + `Menu` | Barra lateral `bg.sidebar` y contenido sobre `bg.canvas`. |
| Toast | `notification` / `message` de Ant Design con el estilo de `screens/src/_base.css` | Éxito e información se cierran a los 5 s (pausa al pasar el mouse); los errores se quedan hasta cerrarlos. Máximo 3. Arriba a la derecha en web, abajo en móvil. `role="status"` para éxito e información y `role="alert"` para errores. |
| Visor de documentos | Componente propio sobre PDF.js | Zoom, páginas, girar y descargar por URL prefirmada. Las imágenes se muestran directo. |
| Carga de documentos | `Upload.Dragger` en web; en móvil, botones "Tomar foto" y "Elegir archivo" | Valida tipo y tamaño antes de enviar; muestra subida, análisis antivirus y resultado. |

## Reglas visuales

- **Etiquetas:** nada de mayúsculas espaciadas. Encabezados de tabla, etiquetas de KPI, grupos del menú y grupos de listas van en minúscula inicial, `text.xs` (12 px), peso medio. No se usan tamaños fuera de la escala (no hay 11 px).
- **Enlaces en texto:** un enlace dentro de un bloque de texto (párrafo, ayuda, mensaje) va subrayado siempre, no solo al pasar el mouse. El color solo no alcanza para distinguirlo del texto que lo rodea (WCAG 1.4.1). Los enlaces que no están dentro de texto corrido (menú, migas, botones de texto) no lo necesitan.
- **Sombras:** las tarjetas que están en el flujo de la página llevan borde y fondo, sin sombra. `shadow.md` y `shadow.lg` son solo para lo que flota: menús, toasts, drawer y hojas inferiores.
- **Teal es estado, no avance:** las barras de completitud siempre van en `brand.primary`. El teal (`accent`) queda para "Lista para radicar" y exonerado.
- **Conteos de alerta sobre color sólido** (documentos pendientes en la navegación del portal): `tone.danger.solid` con `tone.danger.onSolid`.
- **Menú lateral:** colores desde `sidebar.itemHover`, `sidebar.itemActive`, `sidebar.divider` y `text.onSidebarStrong`; nada escrito a mano.
- **Una acción principal por vista, y que se pueda ejecutar.** Si la acción natural está bloqueada (por ejemplo, "Marcar lista para radicar" con documentos pendientes), queda deshabilitada con la razón visible, y el primario pasa a lo que desbloquea ("Revisar 3 documentos").
- **El comprador ve una sola métrica de avance:** "10 de 16 documentos listos", igual en el inicio y en la pantalla de documentos. El porcentaje interno de completitud es del backoffice.
- **Lo destructivo no se destaca:** "Ya no quiero continuar" va en `text.secondary`; lo urgente (vencimiento del acceso) va arriba, en la tarjeta de estado.

## Accesibilidad

- Contraste verificado en el build (`generated/contrast-report.md`): texto normal 4,5:1 y elementos de interfaz 3:1, en los dos temas. Incluye texto terciario sobre fondos de fila seleccionada (`brand.subtle`), sobre `bg.canvas` y `bg.subtle`.
- Los diálogos con `aria-modal` (drawer de revisión, hojas inferiores) mantienen el foco adentro y lo devuelven al cerrar.
- Íconos que comunican algo (alerta de inactividad) llevan texto oculto, no solo `title`.
- Foco visible con `focus.ring` en todo control interactivo.
- El estado nunca depende solo del color: el badge siempre lleva el texto.
- Los mensajes de error de un campo van debajo del campo y se enlazan con `aria-describedby`.

## Próximos pasos

1. Monorepo: `specs/TAREA-monorepo.md`.
2. Base del frontend y reparto en dos agentes: `specs/TAREA-frontend-base.md`.
3. Campos del listado que faltan en la API: `specs/TAREA-applications-listado.md`.
