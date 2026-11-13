import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppShell, AppShellSkeleton, useShellTrail } from "@/components/ui/app-shell";
import { HouseIcon } from "@/components/ui/icons";
import { groupNav, NAV_ITEMS, type NavItem } from "@/lib/navigation/nav-config";
import { ThemeProvider } from "@/providers/theme-provider";

vi.mock("next/navigation", () => ({ usePathname: () => "/solicitudes/abc" }));

const ITEMS: NavItem[] = [
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "a",
  },
  {
    href: "/clientes",
    label: "Clientes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "b",
  },
  {
    href: "/usuarios",
    label: "Usuarios",
    icon: <HouseIcon />,
    group: "Configuración",
    permission: "c",
  },
];

function renderShell(onLogout = vi.fn()) {
  render(
    <ThemeProvider initialMode="light" hasCookie>
      <AppShell
        nav={groupNav(ITEMS)}
        user={{ name: "Asesora Pruebas E2E", email: "asesor@example.com" }}
        onLogout={onLogout}
      >
        <h1>Contenido</h1>
      </AppShell>
    </ThemeProvider>,
  );
  return onLogout;
}

describe("groupNav", () => {
  it("agrupa en orden y no devuelve grupos vacíos", () => {
    expect(groupNav(ITEMS).map((g) => [g.label, g.items.length])).toEqual([
      ["Comercial", 2],
      ["Configuración", 1],
    ]);
    expect(groupNav([])).toEqual([]);
    expect(NAV_ITEMS.map((i) => i.permission)).toEqual(["applications.read"]);
  });
});

describe("AppShell", () => {
  it("marca la entrada activa, los grupos y la ruta en la barra superior", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getByRole("link", { name: "Solicitudes" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Clientes" })).not.toHaveAttribute("aria-current");
    expect(within(nav).getByText("Configuración")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Comercial/Solicitudes");
    expect(screen.getByRole("main")).toHaveTextContent("Contenido");
    expect(screen.getByRole("link", { name: "Saltar al contenido" })).toHaveAttribute(
      "href",
      "#contenido",
    );
  });

  it("una página agrega su última miga y la entrada del menú pasa a ser enlace", () => {
    function Page() {
      useShellTrail("SOL-000182");
      return <h1>Expediente</h1>;
    }
    render(
      <ThemeProvider initialMode="light" hasCookie>
        <AppShell
          nav={groupNav(ITEMS)}
          user={{ name: "A", email: "a@example.com" }}
          onLogout={vi.fn()}
        >
          <Page />
        </AppShell>
      </ThemeProvider>,
    );
    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("Comercial/Solicitudes/SOL-000182");
    expect(within(banner).getByRole("link", { name: "Solicitudes" })).toHaveAttribute(
      "href",
      "/solicitudes",
    );
  });

  it("el bloque del usuario abre el menú de la cuenta y cierra la sesión", async () => {
    const user = userEvent.setup();
    const onLogout = renderShell();
    const account = screen.getByRole("button", { name: /Asesora Pruebas E2E/ });
    expect(account).toHaveAttribute("aria-haspopup", "menu");
    expect(account).toHaveAttribute("aria-expanded", "false");
    expect(account).toHaveTextContent("asesor@example.com");
    expect(account).toHaveTextContent("AE");

    await user.click(account);
    expect(account).toHaveAttribute("aria-expanded", "true");
    await user.click(await screen.findByRole("menuitem", { name: "Cerrar sesión" }));
    expect(onLogout).toHaveBeenCalledOnce();
  });

  it("el menú lateral se abre en un drawer y se cierra", async () => {
    const user = userEvent.setup();
    renderShell();
    const open = screen.getByRole("button", { name: "Abrir menú" });
    await user.click(open);
    expect(open).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Cerrar menú" }));
    expect(open).toHaveAttribute("aria-expanded", "false");
  });

  it("incluye el botón de tema", () => {
    renderShell();
    expect(screen.getByRole("button", { name: "Cambiar a tema oscuro" })).toBeInTheDocument();
  });
});

describe("AppShellSkeleton", () => {
  it("anuncia la carga", () => {
    render(<AppShellSkeleton />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando…");
  });
});
