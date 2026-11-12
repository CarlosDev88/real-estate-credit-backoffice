import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useMutation } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ApiError, networkError } from "@/lib/api/errors";
import {
  parseTheme,
  persistTheme,
  readStoredTheme,
  THEME_FALLBACK_SCRIPT,
} from "@/lib/theme/theme";
import { AppProviders } from "@/providers/app-providers";
import { useTheme } from "@/providers/theme-provider";
import { useToast } from "@/providers/toast";

function themeCookie(): string | null {
  return document.cookie.match(/(?:^|; )um-theme=([^;]*)/)?.[1] ?? null;
}

afterEach(() => {
  document.documentElement.setAttribute("data-theme", "light");
  vi.restoreAllMocks();
});

describe("lib/theme", () => {
  it("cualquier valor que no sea dark es light", () => {
    expect(parseTheme("dark")).toBe("dark");
    expect(parseTheme("blue")).toBe("light");
    expect(parseTheme(undefined)).toBe("light");
  });

  it("guarda en localStorage y en la cookie", () => {
    persistTheme("dark");
    expect(readStoredTheme()).toBe("dark");
    expect(themeCookie()).toBe("dark");
  });

  it("si localStorage falla, sigue sin romper", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    expect(() => persistTheme("dark")).not.toThrow();
    expect(readStoredTheme()).toBeNull();
  });

  it("el script de respaldo aplica el tema guardado", () => {
    window.localStorage.setItem("um-theme", "dark");
    new Function(THEME_FALLBACK_SCRIPT)();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});

function ThemeProbe() {
  const { mode } = useTheme();
  return <span data-testid="mode">{mode}</span>;
}

describe("ThemeProvider y ThemeToggle", () => {
  it("el botón cambia el tema, el atributo, localStorage y la cookie", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <ThemeToggle />
        <ThemeProbe />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Cambiar a tema oscuro" }));
    expect(screen.getByTestId("mode")).toHaveTextContent("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
    expect(themeCookie()).toBe("dark");
    expect(screen.getByRole("button", { name: "Cambiar a tema claro" })).toBeInTheDocument();
  });

  it("sin cookie toma el tema de localStorage y repone la cookie", async () => {
    window.localStorage.setItem("um-theme", "dark");
    render(
      <AppProviders initialTheme="light" hasThemeCookie={false}>
        <ThemeProbe />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByTestId("mode")).toHaveTextContent("dark"));
    expect(themeCookie()).toBe("dark");
  });

  it("useTheme fuera del provider falla con un mensaje claro", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<ThemeProbe />)).toThrow(/ThemeProvider/);
  });
});

function ToastButtons() {
  const toast = useToast();
  return (
    <>
      <button type="button" onClick={() => toast.success({ title: "Guardado" })}>
        ok
      </button>
      <button
        type="button"
        onClick={() =>
          toast.error({ title: "Falló", action: { label: "Reintentar", onClick: () => {} } })
        }
      >
        error
      </button>
    </>
  );
}

describe("useToast", () => {
  it("éxito con role=status y error con role=alert y acción", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <ToastButtons />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "ok" }));
    await userEvent.click(screen.getByRole("button", { name: "error" }));

    const success = await screen.findByText("Guardado");
    expect(success.closest("[role]")).toHaveAttribute("role", "status");
    expect(success.closest(".um-toast")).toHaveClass("um-toast--success");

    const error = screen.getByText("Falló");
    expect(error.closest("[role]")).toHaveAttribute("role", "alert");
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Cerrar aviso" }).length).toBeGreaterThan(0);
  });
});

function FailingWrite({ error, handles = false }: { error: unknown; handles?: boolean }) {
  const mutation = useMutation({
    meta: { handlesErrors: handles },
    mutationFn: () => Promise.reject(error),
  });
  return (
    <button type="button" onClick={() => mutation.mutate()}>
      escribir
    </button>
  );
}

describe("errores de escritura (MutationCache global)", () => {
  it("toast persistente con el mensaje y el código", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <FailingWrite error={new ApiError(422, "X", "No se pudo guardar.", [], "req-123")} />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "escribir" }));
    const title = await screen.findByText("No se pudo guardar.");
    expect(title.closest("[role]")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Código: req-123")).toBeInTheDocument();
  });

  it("STALE_VERSION ofrece Recargar", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <FailingWrite error={new ApiError(409, "STALE_VERSION", "x", [], "r")} />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "escribir" }));
    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Recargar" }));
  });

  it("sin conexión muestra el aviso de red", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <FailingWrite error={networkError()} />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "escribir" }));
    expect(await screen.findByText(/No hay conexión con el servidor/)).toBeInTheDocument();
  });

  it("con meta.handlesErrors no hay toast global", async () => {
    render(
      <AppProviders initialTheme="light" hasThemeCookie>
        <FailingWrite error={new ApiError(400, "X", "Silencioso")} handles />
      </AppProviders>,
    );
    await userEvent.click(screen.getByRole("button", { name: "escribir" }));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(screen.queryByText("Silencioso")).not.toBeInTheDocument();
  });
});
