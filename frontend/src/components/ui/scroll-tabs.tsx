"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

export interface ScrollTabItem {
  key: string;
  /** Texto de la pestaña: viene de la API (los grupos de estado no los define el frontend). */
  label: string;
  count?: number | null;
}

interface ScrollTabsProps {
  items: ScrollTabItem[];
  value: string;
  onChange: (key: string) => void;
  /** Nombre accesible del grupo ("Filtro rápido por estado"). */
  ariaLabel: string;
  className?: string;
}

const FADE = 48;

function maskFor(left: boolean, right: boolean): string | undefined {
  if (left && right)
    return `linear-gradient(to right, transparent 0, #000 ${FADE}px, #000 calc(100% - ${FADE}px), transparent 100%)`;
  if (left) return `linear-gradient(to right, transparent 0, #000 ${FADE}px)`;
  if (right) return `linear-gradient(to left, transparent 0, #000 ${FADE}px)`;
  return undefined;
}

function Arrow({ dir, onClick }: { dir: -1 | 1; onClick: () => void }) {
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-hidden="true"
      onClick={onClick}
      className={`border-border-default bg-bg-surface text-text-secondary hover:text-text-primary absolute top-1/2 z-[2] grid size-7 -translate-y-1/2 cursor-pointer place-items-center rounded-full border shadow-sm pointer-coarse:hidden ${
        dir < 0 ? "left-0" : "right-0"
      }`}
    >
      <svg viewBox="0 0 20 20" fill="currentColor" width={14} height={14} aria-hidden="true">
        <path
          d={
            dir < 0
              ? "M12.7 4.3 7 10l5.7 5.7-1.4 1.4L4.2 10l7.1-7.1 1.4 1.4Z"
              : "M7.3 4.3 13 10l-5.7 5.7 1.4 1.4 7.1-7.1-7.1-7.1-1.4 1.4Z"
          }
        />
      </svg>
    </button>
  );
}

/**
 * Pestañas que se desplazan sin barra visible, con desvanecido y flechas cuando no
 * caben (mockup `solicitudes.html`). Teclado: flechas, Inicio y Fin mueven el foco;
 * Enter o Espacio eligen (activación manual: cada elección puede pedir datos).
 */
export function ScrollTabs({ items, value, onChange, ariaLabel, className = "" }: ScrollTabsProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const [more, setMore] = useState({ left: false, right: false });
  const [focusKey, setFocusKey] = useState(value);

  const measure = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const left = el.scrollLeft > 1;
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setMore((m) => (m.left === left && m.right === right ? m : { left, right }));
  }, []);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [measure, items.length]);

  // La pestaña elegida siempre queda a la vista.
  useEffect(() => {
    tabRefs.current.get(value)?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [value]);

  const focusTab = (key: string) => {
    setFocusKey(key);
    tabRefs.current.get(key)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((i) => i.key === focusKey);
    const last = items.length - 1;
    const target =
      event.key === "ArrowRight"
        ? items[index >= last ? 0 : index + 1]
        : event.key === "ArrowLeft"
          ? items[index <= 0 ? last : index - 1]
          : event.key === "Home"
            ? items[0]
            : event.key === "End"
              ? items[last]
              : undefined;
    if (!target) return;
    event.preventDefault();
    focusTab(target.key);
  };

  const scrollBy = (dir: -1 | 1) => {
    const el = listRef.current;
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.6, behavior: "smooth" });
  };

  // El foco itinerante vuelve a la elegida cuando cambia desde afuera.
  const tabStop = items.some((i) => i.key === focusKey) ? focusKey : value;

  return (
    <div
      className={`relative min-w-0 shadow-[inset_0_-1px_0_var(--um-border-default)] ${className}`}
    >
      {more.left && <Arrow dir={-1} onClick={() => scrollBy(-1)} />}
      <div
        ref={listRef}
        role="tablist"
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        className="flex gap-1 overflow-x-auto overflow-y-hidden scroll-smooth [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={{ maskImage: maskFor(more.left, more.right), scrollPaddingInline: 40 }}
      >
        {items.map((item) => {
          const selected = item.key === value;
          return (
            <button
              key={item.key}
              ref={(el) => {
                if (el) tabRefs.current.set(item.key, el);
                else tabRefs.current.delete(item.key);
              }}
              type="button"
              role="tab"
              aria-selected={selected}
              tabIndex={item.key === tabStop ? 0 : -1}
              onFocus={() => setFocusKey(item.key)}
              onClick={() => onChange(item.key)}
              className={`inline-flex flex-none cursor-pointer items-center gap-2 border-0 bg-transparent px-3 pt-2 pb-2.5 text-sm font-medium whitespace-nowrap ${
                selected
                  ? "text-text-link shadow-[inset_0_-2px_0_var(--um-brand-primary)]"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {item.label}
              {/* Espacio para el nombre accesible ("Todas 48"); en flex no se ve. */}
              {item.count !== undefined && item.count !== null && " "}
              {item.count !== undefined && item.count !== null && (
                <span
                  className={`text-xs font-normal tabular-nums ${selected ? "text-text-link" : "text-text-tertiary"}`}
                >
                  {item.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {more.right && <Arrow dir={1} onClick={() => scrollBy(1)} />}
    </div>
  );
}
