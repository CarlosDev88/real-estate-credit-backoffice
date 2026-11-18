"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

// Estado de "Mi día" en la URL (`/mi-dia?tab=tareas&due=overdue`): la pestaña, los filtros
// de la bandeja y los de las tareas. Los valores por defecto no se escriben.

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;

export const TABS = ["bandeja", "tareas"] as const;
export type Tab = (typeof TABS)[number];
export const DEFAULT_TAB: Tab = "bandeja";

/** Campos que la API sabe ordenar (`ordering_fields` de `GET /workday/applications`). */
export const SORTABLE_FIELDS = ["code", "days_in_stage", "updated_at"] as const;

/** `due` de `GET /tasks`. */
export const DUE_VALUES = ["overdue", "today", "upcoming"] as const;
export type Due = (typeof DUE_VALUES)[number];

/** `status` de `GET /tasks`. Sin valor en la URL: las pendientes. `all`: todas. */
export const TASK_STATUSES = ["PENDING", "COMPLETED", "CANCELLED"] as const;
export const DEFAULT_TASK_STATUS = "PENDING";
export const ALL = "all";

export interface TrayParams {
  search: string;
  stage: string;
  bank_id: string;
  purpose: string;
  attention: string;
  advisor_id: string;
  /** `""`: el orden de la API (primero lo que pide atención). */
  ordering: string;
  page: number;
  page_size: number;
}

export interface TaskParams {
  due: string;
  /** `PENDING` (por defecto), `COMPLETED`, `CANCELLED` o `all`. */
  task_status: string;
  priority: string;
  /** `""`: el usuario actual; `all`: todos (solo el administrador); o un id. */
  assigned_to_id: string;
  task_page: number;
  task_page_size: number;
}

export interface MyDayParams extends TrayParams, TaskParams {
  tab: Tab;
}

const DEFAULTS: MyDayParams = {
  tab: DEFAULT_TAB,
  search: "",
  stage: "",
  bank_id: "",
  purpose: "",
  attention: "",
  advisor_id: "",
  ordering: "",
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  due: "",
  task_status: DEFAULT_TASK_STATUS,
  priority: "",
  assigned_to_id: "",
  task_page: 1,
  task_page_size: DEFAULT_PAGE_SIZE,
};

const ORDER = Object.keys(DEFAULTS) as (keyof MyDayParams)[];

const TRAY_KEYS: (keyof TrayParams)[] = [
  "search",
  "stage",
  "bank_id",
  "purpose",
  "attention",
  "advisor_id",
  "ordering",
  "page",
  "page_size",
];
const TASK_KEYS: (keyof TaskParams)[] = [
  "due",
  "task_status",
  "priority",
  "assigned_to_id",
  "task_page",
  "task_page_size",
];

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

function pageSize(value: string | null): number {
  const n = positiveInt(value);
  return n && (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
}

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  const v = value ?? "";
  return (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

/** `-days_in_stage` y `code` valen; un campo desconocido vuelve al orden de la API. */
export function parseOrdering(value: string | null): string {
  const raw = value ?? "";
  const field = raw.startsWith("-") ? raw.slice(1) : raw;
  return (SORTABLE_FIELDS as readonly string[]).includes(field) ? raw : "";
}

/**
 * Lee la URL con los valores por defecto. Un `due` en la URL sin `tab` abre las tareas
 * (los enlaces del dashboard).
 */
export function parseMyDayParams(search: URLSearchParams): MyDayParams {
  const text = (key: string) => (search.get(key) ?? "").trim();
  const due = oneOf(search.get("due"), [...DUE_VALUES, ""] as const, "");
  return {
    tab: oneOf(search.get("tab"), TABS, due ? "tareas" : DEFAULT_TAB),
    search: text("search"),
    stage: text("stage"),
    bank_id: text("bank_id"),
    purpose: text("purpose"),
    attention: text("attention"),
    advisor_id: text("advisor_id"),
    ordering: parseOrdering(search.get("ordering")),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: pageSize(search.get("page_size")),
    due,
    task_status: oneOf(search.get("task_status"), [...TASK_STATUSES, ALL], DEFAULT_TASK_STATUS),
    priority: text("priority"),
    assigned_to_id: text("assigned_to_id"),
    task_page: positiveInt(search.get("task_page")) ?? 1,
    task_page_size: pageSize(search.get("task_page_size")),
  };
}

/** Query string sin los valores por defecto. */
export function serializeMyDayParams(params: MyDayParams): string {
  const out = new URLSearchParams();
  // La pestaña va primero. La de por defecto depende de `due`: con `due`, "bandeja" se
  // escribe para no saltar a las tareas al recargar.
  if (params.tab !== DEFAULT_TAB || params.due) out.set("tab", params.tab);
  for (const key of ORDER) {
    const value = params[key];
    if (key !== "tab" && value !== "" && value !== DEFAULTS[key]) out.set(key, String(value));
  }
  return out.toString();
}

export function trayOf(params: MyDayParams): TrayParams {
  return Object.fromEntries(TRAY_KEYS.map((k) => [k, params[k]])) as unknown as TrayParams;
}

export function tasksOf(params: MyDayParams): TaskParams {
  return Object.fromEntries(TASK_KEYS.map((k) => [k, params[k]])) as unknown as TaskParams;
}

/** Quita los vacíos: es lo que se manda a la API. */
export function compact<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined),
  ) as Partial<T>;
}

/**
 * Estado de la URL y `update`. Cambiar un filtro de la bandeja vuelve a su página 1, y uno
 * de las tareas, a la página 1 de las tareas.
 */
export function useMyDayParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseMyDayParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<MyDayParams>) => {
      const keys = Object.keys(patch);
      const resets: Partial<MyDayParams> = {};
      if (keys.some((k) => k !== "page" && k !== "tab" && (TRAY_KEYS as string[]).includes(k)))
        resets.page = 1;
      if (keys.some((k) => k !== "task_page" && (TASK_KEYS as string[]).includes(k)))
        resets.task_page = 1;
      const qs = serializeMyDayParams({ ...params, ...resets, ...patch });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
