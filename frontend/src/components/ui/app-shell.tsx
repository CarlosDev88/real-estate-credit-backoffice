"use client";

import { Button, Drawer, Dropdown } from "antd";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";

import { CloseIcon, LogoMark, MenuIcon } from "@/components/ui/icons";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { NavGroup, NavItem } from "@/lib/navigation/nav-config";

export interface ShellUser {
  name: string;
  email: string;
}

interface AppShellProps {
  /** Grupos ya filtrados por permiso. */
  nav: NavGroup[];
  user: ShellUser;
  onLogout: () => void;
  /** Ruta activa; por defecto, la ruta actual. */
  activeHref?: string;
  children: ReactNode;
}

function isActive(item: NavItem, path: string): boolean {
  return path === item.href || path.startsWith(`${item.href}/`);
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts.slice(0, 1);
  return letters.map((p) => p?.charAt(0).toUpperCase() ?? "").join("");
}

/** Bloque del usuario: abre hacia arriba el menú de la cuenta. */
function UserMenu({ user, onLogout }: { user: ShellUser; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-sidebar-divider mt-auto border-t pt-3">
      <Dropdown
        trigger={["click"]}
        placement="topLeft"
        autoFocus
        open={open}
        onOpenChange={setOpen}
        menu={{
          items: [{ key: "logout", label: "Cerrar sesión" }],
          onClick: ({ key }) => {
            setOpen(false);
            if (key === "logout") onLogout();
          },
        }}
      >
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          className="hover:bg-sidebar-item-hover flex w-full cursor-pointer items-center gap-3 rounded-md border-0 bg-transparent px-2 py-1.5 text-left text-inherit"
        >
          <span
            aria-hidden="true"
            className="bg-sidebar-item-active text-text-on-sidebar-strong grid size-8 flex-none place-items-center rounded-full text-xs font-semibold"
          >
            {initials(user.name)}
          </span>
          <span className="min-w-0">
            <span className="text-text-on-sidebar-strong block truncate text-sm font-medium">
              {user.name}
            </span>
            <span className="block truncate text-xs opacity-70">{user.email}</span>
          </span>
        </button>
      </Dropdown>
    </div>
  );
}

function SidebarContent({
  nav,
  activePath,
  user,
  onLogout,
  onNavigate,
  onClose,
}: {
  nav: NavGroup[];
  activePath: string;
  user: ShellUser;
  onLogout: () => void;
  onNavigate?: () => void;
  onClose?: () => void;
}) {
  return (
    <div className="bg-bg-sidebar text-text-on-sidebar relative flex h-full flex-col px-3 py-4">
      <div className="text-text-on-sidebar-strong inline-flex items-center gap-2 px-2 pt-1 pb-6 text-lg font-semibold tracking-tight">
        <LogoMark size={26} />
        Umbral
      </div>
      {onClose && (
        <Button
          type="text"
          aria-label="Cerrar menú"
          icon={<CloseIcon />}
          onClick={onClose}
          className="text-text-on-sidebar-strong! hover:bg-sidebar-item-hover! absolute! top-2.5 right-2"
        />
      )}
      <nav aria-label="Principal" className="flex flex-col gap-0.5">
        {nav.map((group) => (
          <div key={group.label ?? "_"} className="flex flex-col gap-0.5">
            {group.label && (
              <div className="px-3 pt-5 pb-1 text-xs font-medium opacity-70">{group.label}</div>
            )}
            {group.items.map((item) => {
              const active = isActive(item, activePath);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm no-underline ${
                    active
                      ? "bg-sidebar-item-active text-text-on-sidebar-strong font-medium"
                      : "hover:bg-sidebar-item-hover text-inherit"
                  }`}
                >
                  <span className="flex opacity-85">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <UserMenu user={user} onLogout={onLogout} />
    </div>
  );
}

/** Esqueleto del shell mientras se confirma la sesión (`/auth/me`). */
export function AppShellSkeleton() {
  return (
    <div
      className="grid min-h-screen grid-cols-1 min-[861px]:grid-cols-[232px_minmax(0,1fr)]"
      aria-busy="true"
    >
      <div className="bg-bg-sidebar hidden min-[861px]:block" />
      <div className="min-w-0">
        <div className="bg-bg-surface border-border-default h-14 border-b" />
        <div className="p-4 min-[861px]:p-6">
          <span className="sr-only" role="status">
            Cargando…
          </span>
          <div className="bg-bg-muted h-8 w-48 animate-pulse rounded-md motion-reduce:animate-none" />
          <div className="bg-bg-muted mt-3 h-4 w-80 max-w-full animate-pulse rounded-md motion-reduce:animate-none" />
        </div>
      </div>
    </div>
  );
}

/**
 * Shell del backoffice (mockups `solicitudes.html` y `solicitud.html`): barra lateral,
 * barra superior y, en pantallas de 860 px o menos, menú lateral en un drawer.
 */
export function AppShell({ nav, user, onLogout, activeHref, children }: AppShellProps) {
  const pathname = usePathname();
  const activePath = activeHref ?? pathname;
  const [drawerOpen, setDrawerOpen] = useState(false);

  const current = nav.flatMap((g) => g.items).find((item) => isActive(item, activePath));

  return (
    <div className="grid min-h-screen grid-cols-1 min-[861px]:grid-cols-[232px_minmax(0,1fr)]">
      <a
        href="#contenido"
        className="bg-bg-surface text-text-link sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Saltar al contenido
      </a>

      <aside
        aria-label="Menú principal"
        className="sticky top-0 z-30 hidden h-screen overflow-y-auto min-[861px]:block"
      >
        <SidebarContent nav={nav} activePath={activePath} user={user} onLogout={onLogout} />
      </aside>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        placement="left"
        size={264}
        closable={false}
        aria-label="Menú principal"
        styles={{ body: { padding: 0 } }}
      >
        <SidebarContent
          nav={nav}
          activePath={activePath}
          user={user}
          onLogout={onLogout}
          onNavigate={() => setDrawerOpen(false)}
          onClose={() => setDrawerOpen(false)}
        />
      </Drawer>

      <div className="min-w-0">
        <header className="bg-bg-surface border-border-default sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-3 min-[861px]:px-6">
          <Button
            type="text"
            className="min-[861px]:hidden!"
            aria-label="Abrir menú"
            aria-expanded={drawerOpen}
            icon={<MenuIcon />}
            onClick={() => setDrawerOpen(true)}
          />
          {current && (
            <div className="text-text-tertiary flex min-w-0 items-center gap-2 text-sm">
              {current.group && (
                <>
                  <span className="hidden min-[861px]:inline">{current.group}</span>
                  <span aria-hidden="true" className="hidden min-[861px]:inline">
                    /
                  </span>
                </>
              )}
              <b className="text-text-primary truncate font-medium">{current.label}</b>
            </div>
          )}
          <div className="flex-1" />
          <ThemeToggle />
        </header>
        <main id="contenido" tabIndex={-1} className="p-4 outline-none min-[861px]:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
