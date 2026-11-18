import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppProviders } from "@/providers/app-providers";

import { FormPattern, ListFiltersPattern, StatesPattern } from "./ejemplos";

function renderWithApp(ui: React.ReactElement) {
  return render(
    <AppProviders initialTheme="light" hasThemeCookie>
      {ui}
    </AppProviders>,
  );
}

// Escriben varios campos: bajo la carga de la suite completa superan los 5 s por defecto.
describe("patrón de formulario", { timeout: 15_000 }, () => {
  it("valida en el cliente y lleva el error de la API a su campo y el resto al toast", async () => {
    renderWithApp(<FormPattern />);
    await userEvent.click(screen.getByRole("button", { name: "Crear cliente" }));
    expect(await screen.findByText("Escribe el nombre completo.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: "Nombre completo" }), "Ana Restrepo");
    await userEvent.type(screen.getByRole("textbox", { name: "Correo" }), "ana@correo.co");
    await userEvent.click(screen.getByRole("button", { name: "Crear cliente" }));

    const documento = screen.getByRole("textbox", { name: "Número de documento" });
    expect(await screen.findByText("Ya existe un cliente con este documento.")).toBeInTheDocument();
    expect(documento).toHaveAttribute("aria-invalid", "true");
    expect(await screen.findByText("El correo no se pudo verificar.")).toBeInTheDocument();
  });

  it("con datos válidos crea el cliente", async () => {
    renderWithApp(<FormPattern />);
    await userEvent.type(screen.getByRole("textbox", { name: "Nombre completo" }), "Luis Ortiz");
    await userEvent.type(screen.getByRole("textbox", { name: "Correo" }), "luis@correo.co");
    const documento = screen.getByRole("textbox", { name: "Número de documento" });
    await userEvent.clear(documento);
    await userEvent.type(documento, "80123456");
    await userEvent.click(screen.getByRole("button", { name: "Crear cliente" }));
    expect(await screen.findByText("Cliente creado")).toBeInTheDocument();
  });
});

describe("patrón de lista con filtros", () => {
  it("la URL refleja los filtros y Limpiar la deja sin parámetros", async () => {
    renderWithApp(<ListFiltersPattern />);
    expect(screen.getByText("/clientes?origin=FAIR&page=2")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: /Buscar clientes/ }), "ana");
    expect(screen.getByText("/clientes?search=ana&origin=FAIR")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Limpiar" }));
    expect(screen.getByText("/clientes")).toBeInTheDocument();
  });

  it("quitar el chip del origen lo saca de la URL", async () => {
    renderWithApp(<ListFiltersPattern />);
    await userEvent.click(
      screen.getByRole("button", { name: "Quitar filtro Origen: Feria de vivienda" }),
    );
    expect(screen.getByText("/clientes?page=2")).toBeInTheDocument();
  });
});

describe("patrón de estados", () => {
  it("cambia entre cargando, error, vacío y con datos", async () => {
    renderWithApp(<StatesPattern />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando radicaciones");
    await userEvent.click(screen.getByText("Error"));
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar las radicaciones");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(screen.getByRole("status")).toHaveTextContent("Cargando radicaciones");
    await userEvent.click(screen.getByText("Vacío"));
    expect(screen.getByText("Todavía no hay radicaciones")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Con datos"));
    expect(screen.getByRole("region", { name: "Radicación #1" })).toBeInTheDocument();
  });
});
