// Bloques de las páginas de fundamentos. Todo sale de design/generated/ (vía ./tokens):
// los colores se pintan con `var(--um-*)` y los valores que se muestran se leen del archivo.

import type { Tone } from "@design/status-tones";
import type { ReactNode } from "react";

import { StatusBadge, TONE_CLASS } from "@/components/ui/status-badge";

import {
  palettes,
  scale,
  semanticColorGroups,
  shadows,
  statusTones,
  tailwindClass,
  tailwindColorNames,
  TONE_ORDER,
  tokens,
  toneUses,
  typeScale,
  type ThemeName,
  type ToneMap,
} from "./tokens";

const THEMES: { id: ThemeName; label: string }[] = [
  { id: "light", label: "Claro" },
  { id: "dark", label: "Oscuro" },
];

const GROUP_LABEL: Record<string, string> = {
  bg: "Fondos",
  border: "Bordes",
  text: "Texto",
  brand: "Marca",
  accent: "Acento",
  focus: "Foco",
  sidebar: "Menú lateral",
  tone: "Tonos de estado",
};

const KIND_LABEL: Record<keyof ToneMap, string> = {
  application: "Solicitud",
  documentSlot: "Documento",
  fileScan: "Análisis antivirus del archivo",
  ruleOutcome: "Regla del banco",
  filing: "Radicación",
  opportunity: "Oportunidad",
};

const cssVar = (name: string) => `var(--${name})`;

/** Contenedor sin los estilos de los documentos de Storybook (`sb-unstyled`). */
function Block({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`sb-unstyled text-md text-text-primary my-4 font-sans ${className}`}>
      {children}
    </div>
  );
}

function Code({ children }: { children: ReactNode }) {
  return <code className="text-text-secondary font-mono text-xs break-all">{children}</code>;
}

/** El mismo contenido en los dos temas, lado a lado (los tokens cambian con `data-theme`). */
export function ThemePair({ children }: { children: (theme: ThemeName) => ReactNode }) {
  return (
    <Block className="grid gap-4 md:grid-cols-2">
      {THEMES.map((theme) => (
        <section
          key={theme.id}
          data-theme={theme.id}
          aria-label={`Tema ${theme.label.toLowerCase()}`}
          className="border-border-default bg-bg-canvas text-text-primary rounded-lg border p-4"
        >
          <p className="text-text-secondary m-0 mb-3 text-xs font-medium">{theme.label}</p>
          {children(theme.id)}
        </section>
      ))}
    </Block>
  );
}

// --- Colores -------------------------------------------------------------------------------

function Swatch({ name, theme, value }: { name: string; theme: ThemeName; value: string }) {
  return (
    <div
      data-theme={theme}
      className="border-border-default bg-bg-surface flex items-center gap-2 rounded-md border p-1.5"
    >
      <span
        aria-hidden="true"
        className="border-border-strong size-8 flex-none rounded-sm border"
        style={{ background: cssVar(name) }}
      />
      <Code>{value}</Code>
    </div>
  );
}

/** Tokens semánticos de color, agrupados, con el valor en claro y en oscuro. */
export function SemanticColors() {
  return (
    <Block className="flex flex-col gap-8">
      {semanticColorGroups(tokens).map((group) => (
        <section key={group.id} aria-labelledby={`colores-${group.id}`}>
          <h3 id={`colores-${group.id}`} className="m-0 mb-3 text-lg font-semibold">
            {GROUP_LABEL[group.id] ?? group.id}
          </h3>
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="text-text-secondary text-xs font-medium">
                <th className="border-border-default w-2/5 border-b py-2 pr-3 font-medium">
                  token
                </th>
                <th className="border-border-default border-b px-3 py-2 font-medium">claro</th>
                <th className="border-border-default border-b py-2 pl-3 font-medium">oscuro</th>
              </tr>
            </thead>
            <tbody>
              {group.tokens.map((token) => {
                const cssName = token.cssVar.slice("um-".length);
                const utility = tailwindClass(cssName, tailwindColorNames);
                return (
                  <tr key={token.cssVar} className="align-top">
                    <td className="border-border-default border-b py-2 pr-3">
                      <div className="font-mono text-sm font-medium">{token.token}</div>
                      <div>
                        <Code>--{token.cssVar}</Code>
                      </div>
                      {utility && (
                        <div>
                          <Code>{utility}</Code>
                        </div>
                      )}
                    </td>
                    <td className="border-border-default border-b px-3 py-2">
                      <Swatch name={token.cssVar} theme="light" value={token.light} />
                    </td>
                    <td className="border-border-default border-b py-2 pl-3">
                      <Swatch name={token.cssVar} theme="dark" value={token.dark} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </Block>
  );
}

/** Paletas primitivas: solo alimentan los tokens semánticos. */
export function Palettes() {
  return (
    <Block className="flex flex-col gap-4">
      {palettes(tokens).map(({ family, colors }) => (
        <section key={family} aria-label={`Paleta ${family}`}>
          <h3 className="text-text-secondary m-0 mb-2 text-xs font-medium">{family}</h3>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2 p-0">
            {colors.map((color) => (
              <li
                key={color.cssVar}
                className="border-border-default bg-bg-surface rounded-md border p-2"
              >
                <span
                  aria-hidden="true"
                  className="border-border-default mb-2 block h-8 rounded-sm border"
                  style={{ background: cssVar(color.cssVar) }}
                />
                <div className="font-mono text-xs font-medium">{color.name}</div>
                <Code>{color.value}</Code>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </Block>
  );
}

// --- Tipografía ----------------------------------------------------------------------------

const SAMPLE = "Solicitud SOL-000184 lista para radicar";

/** Familias (sans y mono) con sus pesos. */
export function TypeFamilies() {
  const weights = scale(tokens, "weight");
  const families = scale(tokens, "font");
  return (
    <Block className="grid gap-4 md:grid-cols-2">
      {families.map((family) => {
        const isMono = family.step === "mono";
        // La mono solo se carga en regular y medio (las únicas que usan los tokens).
        const familyWeights = isMono
          ? weights.filter((w) => w.step === "regular" || w.step === "medium")
          : weights;
        return (
          <section
            key={family.cssVar}
            aria-label={`Familia ${family.step}`}
            className="border-border-default bg-bg-surface rounded-lg border p-4"
          >
            <div className="font-mono text-sm font-medium">font.{family.step}</div>
            <Code>{family.value}</Code>
            <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
              {familyWeights.map((weight) => (
                <li key={weight.cssVar} className="flex items-baseline justify-between gap-3">
                  <span
                    className="text-lg"
                    style={{ fontFamily: cssVar(family.cssVar), fontWeight: cssVar(weight.cssVar) }}
                  >
                    {isMono ? "SOL-000184" : "Umbral"}
                  </span>
                  <Code>
                    weight.{weight.step} · {weight.value}
                  </Code>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </Block>
  );
}

/** Escala tipográfica: tamaño e interlineado de cada paso. */
export function TypeScale() {
  return (
    <Block>
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="text-text-secondary text-xs font-medium">
            <th className="border-border-default border-b py-2 pr-3 font-medium">token</th>
            <th className="border-border-default border-b px-3 py-2 font-medium">tamaño / línea</th>
            <th className="border-border-default border-b py-2 pl-3 font-medium">ejemplo</th>
          </tr>
        </thead>
        <tbody>
          {typeScale(tokens).map((step) => (
            <tr key={step.cssVar} className="align-middle">
              <td className="border-border-default border-b py-3 pr-3">
                <div className="font-mono text-sm font-medium">text.{step.step}</div>
                <Code>text-{step.step}</Code>
              </td>
              <td className="border-border-default border-b px-3 py-3 whitespace-nowrap">
                <Code>
                  {step.value} / {step.leading}
                </Code>
              </td>
              <td
                className="border-border-default border-b py-3 pl-3"
                style={{ fontSize: cssVar(step.cssVar), lineHeight: cssVar(step.leadingVar) }}
              >
                {SAMPLE}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Block>
  );
}

// --- Espaciado y radios ---------------------------------------------------------------------

/** Escala de espaciado. El paso N equivale al N de Tailwind (N × 4 px) cuando el valor cuadra. */
export function SpacingScale() {
  return (
    <Block>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {scale(tokens, "space").map((step) => {
          const matchesTailwind = step.value === `${Number(step.step) * 4}px`;
          return (
            <li key={step.cssVar} className="grid grid-cols-[96px_80px_1fr] items-center gap-3">
              <span className="font-mono text-sm font-medium">space.{step.step}</span>
              <Code>{step.value}</Code>
              <span className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="bg-brand-primary block h-3 rounded-sm"
                  style={{ width: cssVar(step.cssVar) }}
                />
                {matchesTailwind && (
                  <Code>
                    gap-{step.step} · p-{step.step}
                  </Code>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Block>
  );
}

/** Alturas de control: 32 px en el backoffice y 40 px en el portal del comprador. */
export function ControlHeights() {
  const heights = [...tokens.base].filter(([name]) => name.startsWith("control-height"));
  return (
    <Block className="flex flex-wrap items-end gap-4">
      {heights.map(([name, value]) => (
        <figure key={name} className="m-0 flex flex-col items-start gap-2">
          <span
            aria-hidden="true"
            className="border-border-strong bg-bg-surface block w-32 rounded-md border"
            style={{ height: cssVar(`um-${name}`) }}
          />
          <figcaption>
            <div className="font-mono text-sm font-medium">{name.replace(/-/g, ".")}</div>
            <Code>{value}</Code>
          </figcaption>
        </figure>
      ))}
    </Block>
  );
}

export function RadiusScale() {
  return (
    <Block className="flex flex-wrap gap-4">
      {scale(tokens, "radius").map((step) => (
        <figure key={step.cssVar} className="m-0 flex flex-col items-start gap-2">
          <span
            aria-hidden="true"
            className="border-brand-primary bg-brand-subtle block h-16 w-24 border-2"
            style={{ borderRadius: cssVar(step.cssVar) }}
          />
          <figcaption>
            <div className="font-mono text-sm font-medium">radius.{step.step}</div>
            <Code>
              {step.value} · rounded-{step.step}
            </Code>
          </figcaption>
        </figure>
      ))}
    </Block>
  );
}

// --- Sombras ---------------------------------------------------------------------------------

/** Las tres sombras en los dos temas. */
export function ShadowScale() {
  const list = shadows(tokens);
  return (
    <ThemePair>
      {(theme) => (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {list.map((shadow) => (
            <li
              key={shadow.cssVar}
              className="bg-bg-surface rounded-lg p-4"
              style={{ boxShadow: cssVar(shadow.cssVar) }}
            >
              <div className="font-mono text-sm font-medium">{shadow.token}</div>
              <Code>{theme === "dark" ? shadow.dark : shadow.light}</Code>
            </li>
          ))}
        </ul>
      )}
    </ThemePair>
  );
}

/** Ejemplo de la regla: en el flujo, borde y fondo; la sombra es para lo que flota. */
export function ShadowRule() {
  return (
    <DoDont
      good={
        <div className="flex flex-col gap-3">
          <div className="border-border-default bg-bg-surface rounded-lg border p-4">
            <div className="font-medium">Resumen de la solicitud</div>
            <div className="text-text-secondary text-sm">Tarjeta en el flujo: borde y fondo.</div>
          </div>
          <div
            className="bg-bg-surface border-border-default ml-auto w-48 rounded-md border p-2 text-sm"
            style={{ boxShadow: cssVar("um-shadow-md") }}
          >
            Menú que flota: <span className="font-mono">shadow.md</span>
          </div>
        </div>
      }
      goodNote="Las tarjetas del flujo llevan borde y fondo. shadow.md y shadow.lg, solo para menús, toasts, drawer y hojas inferiores."
      bad={
        <div className="bg-bg-surface rounded-lg p-4" style={{ boxShadow: cssVar("um-shadow-lg") }}>
          <div className="font-medium">Resumen de la solicitud</div>
          <div className="text-text-secondary text-sm">Tarjeta en el flujo con sombra.</div>
        </div>
      }
      badNote="Una tarjeta que no flota con sombra: compite con lo que sí flota y ensucia la jerarquía."
    />
  );
}

// --- Tonos de estado -------------------------------------------------------------------------

function ToneSample({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span
      data-tone={tone}
      className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium whitespace-nowrap ${TONE_CLASS[tone]}`}
    >
      <span aria-hidden="true" className="size-1.5 flex-none rounded-full bg-current" />
      {label}
    </span>
  );
}

/** Los seis tonos, con su uso según el README, en los dos temas. */
export function ToneLegend() {
  return (
    <ThemePair>
      {() => (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {TONE_ORDER.map((tone) => (
            <li key={tone} className="grid grid-cols-[96px_1fr] items-start gap-3">
              <ToneSample tone={tone} label={tone} />
              <span className="text-text-secondary text-sm">{toneUses[tone]}</span>
            </li>
          ))}
        </ul>
      )}
    </ThemePair>
  );
}

/**
 * Tono de cada código, leído de status-tones.ts. El texto del badge aquí es el código; en la
 * app siempre es la etiqueta que manda la API.
 */
export function ToneMapTable() {
  return (
    <Block className="flex flex-col gap-6">
      {(Object.keys(statusTones) as (keyof ToneMap)[]).map((kind) => (
        <section key={kind} aria-labelledby={`tonos-${kind}`}>
          <h3 id={`tonos-${kind}`} className="m-0 mb-1 text-lg font-semibold">
            {KIND_LABEL[kind] ?? kind}
          </h3>
          <p className="m-0 mb-3">
            <Code>toneFor(&quot;{kind}&quot;, código)</Code>
          </p>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-2 p-0">
            {Object.entries(statusTones[kind]).map(([code, tone]) => (
              <li
                key={code}
                className="border-border-default bg-bg-surface flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
              >
                <StatusBadge kind={kind} code={code} label={code} />
                <Code>{tone}</Code>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </Block>
  );
}

/** "El estado nunca solo por color": el badge siempre lleva el texto. */
export function ToneRule() {
  return (
    <DoDont
      good={
        <div className="flex flex-wrap gap-2">
          <StatusBadge kind="application" code="APPROVED" label="Aprobada" />
          <StatusBadge kind="application" code="WAITING_DOCUMENTS" label="Esperando documentos" />
          <StatusBadge kind="application" code="REJECTED" label="Rechazada" />
        </div>
      }
      goodNote="Punto de color más la etiqueta de la API. Se entiende sin ver el color (WCAG 1.4.1)."
      bad={
        <div className="flex gap-3">
          {(["success", "warning", "danger"] as Tone[]).map((tone) => (
            <span
              key={tone}
              aria-hidden="true"
              className={`block size-3 rounded-full border ${TONE_CLASS[tone]}`}
              style={{ background: "currentColor" }}
            />
          ))}
        </div>
      }
      badNote="Solo un punto o un fondo de color: quien no distingue colores, o un lector de pantalla, no sabe el estado."
    />
  );
}

// --- Así sí / así no -------------------------------------------------------------------------

interface DoDontProps {
  good: ReactNode;
  goodNote: string;
  bad: ReactNode;
  badNote: string;
}

/** Ejemplo correcto e incorrecto. El veredicto va en texto, no solo en el color del borde. */
export function DoDont({ good, goodNote, bad, badNote }: DoDontProps) {
  return (
    <Block className="grid gap-4 md:grid-cols-2">
      <figure className="border-tone-success-border bg-bg-surface m-0 rounded-lg border-2 p-4">
        <div className="mb-3">{good}</div>
        <figcaption className="text-sm">
          <strong className="text-tone-success-fg font-semibold">Así sí. </strong>
          <span className="text-text-secondary">{goodNote}</span>
        </figcaption>
      </figure>
      <figure className="border-tone-danger-border bg-bg-surface m-0 rounded-lg border-2 p-4">
        <div className="mb-3">{bad}</div>
        <figcaption className="text-sm">
          <strong className="text-tone-danger-fg font-semibold">Así no. </strong>
          <span className="text-text-secondary">{badNote}</span>
        </figcaption>
      </figure>
    </Block>
  );
}
