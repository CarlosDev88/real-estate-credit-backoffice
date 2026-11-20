// Páginas, usuarios y condiciones de la medición (Parte 1 y Parte 4 usan lo mismo).
export const BASE_URL = process.env.PERF_BASE_URL ?? "http://localhost:3003";
export const DEMO_PASSWORD = "DemoUmbral2026!";

export const USERS = {
  admin: "admin@demo.local",
  asesora: "asesora.lucia@demo.local",
  broker: "broker@demo.local",
};

/**
 * Las 12 páginas. `path` puede ser una función que recibe el contexto (ids que se
 * resuelven al arrancar: el expediente y el enlace del comprador).
 */
export const PAGES = [
  { id: "login", role: "public", path: "/login", heading: "Iniciar sesión" },
  { id: "aceptar-invitacion", role: "public", path: "/aceptar-invitacion" },
  { id: "acceso", role: "public", path: "/acceso" },
  { id: "dashboard", role: "admin", path: "/dashboard" },
  { id: "reportes", role: "admin", path: "/reportes" },
  { id: "admin-usuarios", role: "admin", path: "/admin/usuarios" },
  { id: "mi-dia", role: "asesora", path: "/mi-dia" },
  { id: "solicitudes", role: "asesora", path: "/solicitudes" },
  { id: "expediente", role: "asesora", path: (ctx) => `/solicitudes/${ctx.dossierId}` },
  { id: "clientes", role: "asesora", path: "/clientes" },
  { id: "mis-comisiones", role: "asesora", path: "/mis-comisiones" },
  { id: "prospectos", role: "broker", path: "/prospectos" },
  { id: "portal", role: "buyer", path: "/portal" },
];

export const ROLES = ["public", "admin", "asesora", "broker", "buyer"];

// Web Vitals de laboratorio: escritorio del backoffice con CPU ×4 (portátil modesto).
export const VITALS_VIEWPORT = { width: 1440, height: 900 };
export const VITALS_CPU_RATE = 4;

export const RUNS = Number(process.env.PERF_RUNS ?? 5);
