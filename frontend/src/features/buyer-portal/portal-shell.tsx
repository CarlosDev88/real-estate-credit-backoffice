"use client";

import { Dropdown } from "antd";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import { PortalLogo } from "@/features/buyer-portal/portal-notice";
import type { BuyerApplicationRef } from "@/features/buyer-portal/queries";

export const PORTAL_HOME = "/portal";
export const PORTAL_DOCUMENTS = "/portal/documentos";

const iconProps = {
  viewBox: "0 0 20 20",
  fill: "currentColor",
  "aria-hidden": true,
  focusable: false,
} as const;

function HomeIcon({ size }: { size: number }) {
  return (
    <svg {...iconProps} width={size} height={size}>
      <path d="M10 2 2 8v10h5v-6h6v6h5V8l-8-6Z" />
    </svg>
  );
}

function DocumentIcon({ size }: { size: number }) {
  return (
    <svg {...iconProps} width={size} height={size}>
      <path d="M5 2h7l4 4v12H5V2Zm2 7v2h7V9H7Zm0 4v2h7v-2H7Z" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg {...iconProps} width={16} height={16} className="mt-0.5 flex-none">
      <path d="M6 8V6a4 4 0 1 1 8 0v2h1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h1Zm2 0h4V6a2 2 0 1 0-4 0v2Z" />
    </svg>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts.slice(0, 1);
  return letters.map((p) => p?.charAt(0).toUpperCase() ?? "").join("");
}

interface NavEntry {
  href: string;
  label: string;
  icon: (size: number) => ReactNode;
  /** Conteo de alerta (documentos que le tocan al comprador). */
  count?: number;
}

function isActive(href: string, path: string): boolean {
  if (href === PORTAL_HOME) return path === PORTAL_HOME;
  return path === href || path.startsWith(`${href}/`);
}

function CountBadge({ count, className }: { count: number; className: string }) {
  return (
    <span
      className={`bg-tone-danger-solid text-tone-danger-on-solid rounded-full text-xs font-semibold tabular-nums ${className}`}
    >
      {count}
      <span className="sr-only"> pendientes</span>
    </span>
  );
}

/** Franja de solicitud cerrada o sin cambios (`is_closed` / `!is_editable`). */
export function ReadOnlyBanner({ application }: { application: BuyerApplicationRef }) {
  if (!application.is_closed && application.is_editable) return null;
  const title = application.is_closed
    ? "Tu solicitud está cerrada"
    : "Tu solicitud ya no admite cambios";
  return (
    <div
      role="status"
      className="bg-tone-neutral-bg text-tone-neutral-fg border-tone-neutral-border border-b"
    >
      <p className="m-0 mx-auto flex max-w-[1200px] items-start gap-2 px-4 py-3 text-sm min-[900px]:px-5">
        <LockIcon />
        <span>
          <b className="font-semibold">{title}</b> · {application.public_status_label}
        </span>
      </p>
    </div>
  );
}

interface PortalShellProps {
  buyerName: string;
  application: BuyerApplicationRef;
  /** Documentos con `needs_action`; `undefined` mientras carga. */
  pendingDocuments?: number;
  /** Sin navegación (por ejemplo, con consentimientos pendientes). */
  hideNav?: boolean;
  onLogout: () => void;
  children: ReactNode;
}

/**
 * Marco del portal (mockups `portal.html` y `portal-documentos.html`): móvil primero,
 * con barra inferior fija; desde 900 px, la navegación pasa a la barra superior.
 */
export function PortalShell({
  buyerName,
  application,
  pendingDocuments,
  hideNav = false,
  onLogout,
  children,
}: PortalShellProps) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const nav: NavEntry[] = [
    { href: PORTAL_HOME, label: "Inicio", icon: (s) => <HomeIcon size={s} /> },
    {
      href: PORTAL_DOCUMENTS,
      label: "Documentos",
      icon: (s) => <DocumentIcon size={s} />,
      count: pendingDocuments,
    },
  ];

  return (
    <div
      className={`bg-bg-canvas text-lg min-[900px]:text-md min-h-screen ${
        hideNav ? "" : "pb-[calc(76px+env(safe-area-inset-bottom))] min-[900px]:pb-0"
      }`}
    >
      <a
        href="#contenido"
        className="bg-bg-surface text-text-link sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Saltar al contenido
      </a>
      <header className="bg-bg-surface border-border-default sticky top-0 z-20 border-b">
        <div className="mx-auto flex max-w-[1200px] items-center gap-2 px-4 py-3 min-[900px]:px-5">
          <span className="text-text-primary inline-flex items-center gap-2 text-lg font-semibold tracking-tight">
            <PortalLogo />
            Umbral
          </span>
          {!hideNav && (
            <nav aria-label="Portal" className="ml-6 hidden gap-1 min-[900px]:flex">
              {nav.map((item) => {
                const active = isActive(item.href, pathname);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-md font-medium no-underline ${
                      active
                        ? "bg-brand-subtle text-text-link"
                        : "text-text-secondary hover:bg-bg-muted hover:text-text-primary"
                    }`}
                  >
                    {item.label}
                    {!!item.count && (
                      <CountBadge count={item.count} className="px-1.5 leading-[18px]" />
                    )}
                  </Link>
                );
              })}
            </nav>
          )}
          <span className="flex-1" />
          <ThemeToggle className="size-11!" />
          <div className="hidden flex-col text-sm leading-tight min-[900px]:flex">
            <b className="font-semibold">{buyerName}</b>
            <span className="text-text-tertiary font-mono text-xs">{application.code}</span>
          </div>
          <Dropdown
            trigger={["click"]}
            placement="bottomRight"
            autoFocus
            open={menuOpen}
            onOpenChange={setMenuOpen}
            menu={{
              items: [
                {
                  key: "who",
                  type: "group",
                  label: (
                    <span className="grid">
                      <span className="text-text-primary font-medium">{buyerName}</span>
                      <span className="font-mono text-xs">{application.code}</span>
                    </span>
                  ),
                },
                { key: "logout", label: "Salir" },
              ],
              onClick: ({ key }) => {
                setMenuOpen(false);
                if (key === "logout") onLogout();
              },
            }}
          >
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className="grid size-11 flex-none cursor-pointer place-items-center rounded-full border-0 bg-transparent p-0"
            >
              <span
                aria-hidden="true"
                className="bg-brand-subtle text-text-link grid size-[34px] place-items-center rounded-full text-xs font-semibold"
              >
                {initials(buyerName)}
              </span>
              {/* Nombre accesible como texto, no `aria-label`: las iniciales visibles no forman
                  parte de él y axe marcaría la diferencia (label-content-name-mismatch). */}
              <span className="sr-only">Cuenta de {buyerName}</span>
            </button>
          </Dropdown>
        </div>
      </header>

      <ReadOnlyBanner application={application} />

      <main id="contenido" tabIndex={-1} className="outline-none">
        {children}
      </main>

      {!hideNav && (
        <nav
          aria-label="Navegación del portal"
          className="bg-bg-surface border-border-default fixed bottom-0 left-1/2 z-20 grid w-full max-w-[480px] -translate-x-1/2 grid-cols-2 border-t pb-[env(safe-area-inset-bottom)] min-[900px]:hidden"
        >
          {nav.map((item) => {
            const active = isActive(item.href, pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`relative grid min-h-14 justify-items-center gap-0.5 pt-2.5 pb-2 text-xs no-underline ${
                  active ? "text-text-link font-semibold" : "text-text-tertiary"
                }`}
              >
                {item.icon(22)}
                {item.label}
                {!!item.count && (
                  <CountBadge
                    count={item.count}
                    className="absolute top-1.5 left-[calc(50%+6px)] grid h-[18px] min-w-[18px] place-items-center px-[5px]"
                  />
                )}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}

/** Contenedor de página del portal: una columna de 480 px en móvil, 720 px en escritorio. */
export function PortalPage({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto grid max-w-[480px] gap-5 px-4 py-5 min-[900px]:max-w-[720px] min-[900px]:px-5 min-[900px]:pt-8 min-[900px]:pb-12">
      {children}
    </div>
  );
}
