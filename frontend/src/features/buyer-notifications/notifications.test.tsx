import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { BuyerNotificationsScreen } from "@/features/buyer-notifications/notifications-screen";
import { sortNotifications, type BuyerNotification } from "@/features/buyer-notifications/queries";
import { PortalShell } from "@/features/buyer-portal/portal-shell";
import { sessionFixture } from "@/features/buyer-portal/portal.fixtures";
import { ThemeProvider } from "@/providers/theme-provider";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

vi.mock("next/navigation", () => ({ usePathname: () => "/portal/avisos" }));

const notice = (over: Partial<BuyerNotification>): BuyerNotification => ({
  id: "n-1",
  notification_type: "ACCESS_GRANTED",
  notification_type_label: "Acceso al portal",
  title: "Ya puedes entrar al portal",
  message: "Tu asesor te dio acceso para completar tu solicitud.",
  created_at: "2026-11-10T10:00:00Z",
  read_at: null,
  ...over,
});

const OLD_READ = notice({
  id: "n-old",
  notification_type: "FILED",
  notification_type_label: "Radicación",
  title: "Radicamos tu solicitud",
  created_at: "2026-11-15T10:00:00Z",
  read_at: "2026-11-15T11:00:00Z",
});
const NEW_UNREAD = notice({
  id: "n-new",
  notification_type: "BANK_APPROVED",
  notification_type_label: "Respuesta del banco",
  title: "El banco aprobó tu crédito",
  created_at: "2026-11-17T10:00:00Z",
});
const OLDER_UNREAD = notice({ id: "n-access" });

const page = (items: BuyerNotification[], next: string | null = null, n = 1) => ({
  items,
  page: n,
  page_size: 50,
  total: items.length,
  next,
  previous: null,
});

describe("orden de los avisos", () => {
  it("no leídos primero y, dentro de cada grupo, del más nuevo al más viejo", () => {
    expect(sortNotifications([OLD_READ, OLDER_UNREAD, NEW_UNREAD]).map((n) => n.id)).toEqual([
      "n-new",
      "n-access",
      "n-old",
    ]);
    // Uno que se lee en la visita sigue contando como no leído (no salta).
    expect(
      sortNotifications([OLD_READ, OLDER_UNREAD], (n) => n.id === "n-old").map((n) => n.id),
    ).toEqual(["n-old", "n-access"]);
  });
});

describe("BuyerNotificationsScreen", { timeout: 30_000 }, () => {
  it("lista los no leídos primero, marca uno al abrirlo y marca todos", async () => {
    let items = [OLD_READ, NEW_UNREAD, OLDER_UNREAD];
    const patched: string[] = [];
    let readAll = 0;
    server.use(
      http.get(apiUrl("/buyer/notifications"), () => HttpResponse.json(page(items))),
      http.patch(apiUrl("/buyer/notifications/:id/read"), ({ params }) => {
        patched.push(String(params.id));
        items = items.map((n) =>
          n.id === params.id ? { ...n, read_at: "2026-11-18T10:00:00Z" } : n,
        );
        return HttpResponse.json(items.find((n) => n.id === params.id));
      }),
      http.post(apiUrl("/buyer/notifications/read-all"), () => {
        readAll += 1;
        const count = items.filter((n) => !n.read_at).length;
        items = items.map((n) => ({ ...n, read_at: n.read_at ?? "2026-11-18T10:00:00Z" }));
        return HttpResponse.json({ count });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<BuyerNotificationsScreen />);

    const list = await screen.findByRole("list", { name: "Avisos" });
    expect(screen.getByText("Tienes 2 avisos sin leer.")).toBeInTheDocument();
    const buttons = within(list).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual([
      expect.stringContaining("El banco aprobó tu crédito"),
      expect.stringContaining("Ya puedes entrar al portal"),
      expect.stringContaining("Radicamos tu solicitud"),
    ]);
    expect(within(list).getAllByText("Nuevo")).toHaveLength(2);

    // Abrir uno sin leer lo marca; el mensaje se ve y el aviso no cambia de lugar.
    await user.click(buttons[1]!);
    expect(buttons[1]).toHaveAttribute("aria-expanded", "true");
    const message = document.getElementById(buttons[1]!.getAttribute("aria-controls")!);
    expect(message).toBeVisible();
    expect(message).toHaveTextContent("Tu asesor te dio acceso para completar tu solicitud.");
    await waitFor(() => expect(patched).toEqual(["n-access"]));
    await waitFor(() => expect(within(list).getAllByText("Nuevo")).toHaveLength(1));
    expect(within(list).getAllByRole("button")[1]).toHaveTextContent("Ya puedes entrar");

    // Abrir uno leído no llama a la API; cerrarlo lo oculta.
    await user.click(within(list).getAllByRole("button")[2]!);
    expect(patched).toHaveLength(1);
    await user.click(within(list).getAllByRole("button")[2]!);
    expect(within(list).getAllByRole("button")[2]).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", { name: "Marcar todos como leídos" }));
    expect(await screen.findByText("1 aviso marcado como leído")).toBeInTheDocument();
    expect(readAll).toBe(1);
    expect(await screen.findByText("Estás al día.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Marcar todos como leídos" }),
    ).not.toBeInTheDocument();
  });

  it("sin avisos, con error y con más páginas", async () => {
    let fail = true;
    server.use(
      http.get(apiUrl("/buyer/notifications"), ({ request }) => {
        if (fail) {
          return HttpResponse.json(
            { code: "SERVER_ERROR", message: "Falló.", details: [], request_id: "r" },
            { status: 500, headers: { "X-Request-ID": "r" } },
          );
        }
        const n = Number(new URL(request.url).searchParams.get("page") ?? 1);
        return HttpResponse.json(
          n === 1
            ? page([NEW_UNREAD], "/api/v1/buyer/notifications?page=2")
            : page([OLD_READ], null, 2),
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<BuyerNotificationsScreen />);
    const retry = await screen.findByRole("button", { name: "Reintentar" }, { timeout: 8000 });
    expect(screen.getByText("No pudimos cargar tus avisos")).toBeInTheDocument();
    fail = false;
    await user.click(retry);
    await screen.findByText("El banco aprobó tu crédito");
    await user.click(screen.getByRole("button", { name: "Ver avisos anteriores" }));
    expect(await screen.findByText("Radicamos tu solicitud")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ver avisos anteriores" })).not.toBeInTheDocument();
  });

  it("sin avisos todavía", async () => {
    server.use(http.get(apiUrl("/buyer/notifications"), () => HttpResponse.json(page([]))));
    renderWithProviders(<BuyerNotificationsScreen />);
    expect(await screen.findByText(/Todavía no tienes avisos/)).toBeInTheDocument();
    expect(screen.getByText("Estás al día.")).toBeInTheDocument();
  });
});

describe("navegación del portal", () => {
  it("muestra Avisos con el número sin leer", () => {
    const session = sessionFixture();
    renderWithProviders(
      <ThemeProvider initialMode="light" hasCookie>
        <PortalShell
          buyerName="Sofía Herrera"
          application={session.application}
          unreadNotices={3}
          onLogout={() => {}}
        >
          contenido
        </PortalShell>
      </ThemeProvider>,
    );
    const nav = screen.getByRole("navigation", { name: "Navegación del portal" });
    const link = within(nav).getByRole("link", { name: /Avisos/ });
    expect(link).toHaveAttribute("href", "/portal/avisos");
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveTextContent("3 sin leer");
  });
});
