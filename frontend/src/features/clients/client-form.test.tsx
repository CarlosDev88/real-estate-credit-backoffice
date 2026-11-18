import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  compactPhone,
  EMPTY_CLIENT,
  existingClientId,
  makeClientSchema,
  toCreateBody,
  toUpdateBody,
  todayIso,
  valuesFromClient,
} from "@/features/clients/client-form";
import { ClientDetailScreen } from "@/features/clients/client-detail-screen";
import { EditClientScreen, NewClientScreen } from "@/features/clients/client-screens";
import {
  apiError,
  CLIENTS_BOOTSTRAP,
  CLIENTS_ME,
  makeClientDetail,
} from "@/features/clients/clients.fixtures";
import { ApiError } from "@/lib/api/errors";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/clientes/nuevo",
  useSearchParams: () => new URLSearchParams(),
}));

type User = ReturnType<typeof userEvent.setup>;

function useBaseApi(me: typeof CLIENTS_ME = CLIENTS_ME) {
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(me)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(CLIENTS_BOOTSTRAP)),
  );
}

// En jsdom el nombre accesible de un campo opcional sale "Origen(opcional)", sin el
// espacio: por eso esos campos se buscan con una expresión regular.
async function pick(user: User, label: string | RegExp, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click((await screen.findAllByTitle(option)).at(-1)!);
}

async function fillRequired(user: User) {
  await pick(user, "Tipo de documento", "Cédula de ciudadanía");
  await user.type(screen.getByRole("textbox", { name: "Número de documento" }), "1.032.445.908");
  await user.type(screen.getByRole("textbox", { name: "Nombres" }), " Laura ");
  await user.type(screen.getByRole("textbox", { name: "Apellidos" }), "Gómez Vélez");
}

const submit = (user: User, name = "Crear cliente") =>
  user.click(screen.getByRole("button", { name }));

beforeEach(() => {
  nav.push.mockClear();
});

describe("reglas del formulario de cliente", () => {
  const schema = makeClientSchema("2026-11-17");
  const valid = {
    ...EMPTY_CLIENT,
    document_type_code: "CC",
    document_number: "1032445908",
    first_names: "Laura",
    last_names: "Gómez",
  };
  const messages = (values: typeof valid) => {
    const result = schema.safeParse(values);
    return result.success
      ? {}
      : Object.fromEntries(result.error.issues.map((i) => [i.path[0], i.message]));
  };

  it("pide los obligatorios y acepta los opcionales vacíos", () => {
    expect(messages(valid)).toEqual({});
    expect(messages(EMPTY_CLIENT)).toEqual({
      document_type_code: "Elige el tipo de documento.",
      document_number: "Escribe el número de documento.",
      first_names: "Escribe los nombres.",
      last_names: "Escribe los apellidos.",
    });
  });

  it("valida el formato del documento, el correo, el teléfono y la fecha", () => {
    expect(
      messages({
        ...valid,
        document_number: "10#32",
        email: "laura@",
        phone: "3001234567",
        birth_date: "2026-11-17",
      }),
    ).toEqual({
      document_number: "Usa solo letras, dígitos, puntos o guiones.",
      email: "Escribe un correo válido, como nombre@dominio.com.",
      phone: "Usa el formato internacional, por ejemplo +573001234567.",
      birth_date: "La fecha de nacimiento debe ser anterior a hoy.",
    });
    expect(messages({ ...valid, birth_date: "12/04/1990" })).toEqual({
      birth_date: "Escribe una fecha válida.",
    });
    expect(messages({ ...valid, phone: "+57 (300) 123-4567", birth_date: "1990-04-12" })).toEqual(
      {},
    );
    expect(messages({ ...valid, first_names: "x".repeat(121) })).toEqual({
      first_names: "Máximo 120 caracteres.",
    });
  });

  it("el alta no manda los opcionales vacíos y compacta el teléfono", () => {
    expect(toCreateBody(valid)).toEqual({
      document_type_code: "CC",
      document_number: "1032445908",
      first_names: "Laura",
      last_names: "Gómez",
    });
    expect(
      toCreateBody({
        ...valid,
        email: "a@b.co",
        phone: "+57 300 123 4567",
        birth_date: "1990-04-12",
        origin_type: "BROKER",
      }),
    ).toMatchObject({
      email: "a@b.co",
      phone: "+573001234567",
      birth_date: "1990-04-12",
      origin_type: "BROKER",
    });
  });

  it("la edición manda solo lo cambiado y vaciar un opcional lo borra", () => {
    const values = { ...valid, email: "", phone: "", birth_date: "", origin_type: "" };
    expect(toUpdateBody(values, {})).toEqual({});
    expect(
      toUpdateBody(values, { email: true, phone: true, birth_date: true, origin_type: true }),
    ).toEqual({ email: "", phone: "", birth_date: null, origin_type: null });
    expect(
      toUpdateBody(valid, {
        document_type_code: true,
        document_number: true,
        first_names: true,
        last_names: true,
      }),
    ).toEqual({
      document_type_code: "CC",
      document_number: "1032445908",
      first_names: "Laura",
      last_names: "Gómez",
    });
  });

  it("lee el detalle, el id del cliente existente y la fecha de hoy en Bogotá", () => {
    expect(valuesFromClient(makeClientDetail({ origin: null, birth_date: null }))).toMatchObject({
      document_type_code: "CC",
      birth_date: "",
      origin_type: "",
    });
    const duplicate = new ApiError(409, "DUPLICATE_CLIENT_DOCUMENT", "Ya existe.", [
      {
        field: "document_number",
        code: "EXISTING_CLIENT",
        message: "Usa el cliente existente.",
        resource_id: "cl-9",
      },
    ]);
    expect(existingClientId(duplicate)).toBe("cl-9");
    expect(
      existingClientId(new ApiError(409, "DUPLICATE_CLIENT_DOCUMENT", "Ya existe.")),
    ).toBeNull();
    expect(existingClientId(new Error("x"))).toBeNull();
    // 02:00 UTC del 18 es todavía el 17 en Bogotá (UTC−5).
    expect(todayIso(new Date("2026-11-18T02:00:00Z"))).toBe("2026-11-17");
    expect(compactPhone("+57 (300) 123-4567")).toBe("+573001234567");
  });
});

describe("nuevo cliente", { timeout: 20_000 }, () => {
  it("valida en el front sin llamar a la API", async () => {
    useBaseApi();
    const posted = vi.fn();
    server.use(http.post(apiUrl("/clients"), () => posted()));
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });

    await user.type(screen.getByRole("textbox", { name: /Correo/ }), "laura@");
    await submit(user);
    expect(await screen.findByText("Elige el tipo de documento.")).toBeInTheDocument();
    expect(screen.getByText("Escribe el número de documento.")).toBeInTheDocument();
    expect(
      screen.getByText("Escribe un correo válido, como nombre@dominio.com."),
    ).toBeInTheDocument();
    const number = screen.getByRole("textbox", { name: "Número de documento" });
    expect(number).toHaveAttribute("aria-invalid", "true");
    expect(number).toHaveAccessibleDescription("Escribe el número de documento.");
    expect(posted).not.toHaveBeenCalled();
  });

  it("solo ofrece los valores activos de los catálogos", async () => {
    useBaseApi();
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });

    await user.click(screen.getByRole("combobox", { name: "Tipo de documento" }));
    const types = await screen.findAllByRole("option");
    expect(types.map((o) => o.textContent)).toEqual([
      "Cédula de ciudadanía",
      "Cédula de extranjería",
    ]);
  });

  it("crea el cliente y va a su detalle", async () => {
    useBaseApi();
    let body: unknown;
    server.use(
      http.post(apiUrl("/clients"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeClientDetail({ id: "cl-new" }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });

    await fillRequired(user);
    await user.type(screen.getByRole("textbox", { name: /Teléfono/ }), "+57 310 445 8821");
    await pick(user, /Origen/, "Broker");
    await submit(user);

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/clientes/cl-new"));
    expect(body).toEqual({
      document_type_code: "CC",
      document_number: "1.032.445.908",
      first_names: "Laura",
      last_names: "Gómez Vélez",
      phone: "+573104458821",
      origin_type: "BROKER",
    });
    expect(await screen.findByText("Cliente creado")).toBeInTheDocument();
  });

  it("el documento duplicado va al campo, con enlace al cliente existente", async () => {
    useBaseApi();
    server.use(
      http.post(apiUrl("/clients"), () =>
        HttpResponse.json(
          apiError(
            "DUPLICATE_CLIENT_DOCUMENT",
            "Ya existe un cliente con ese tipo y número de documento.",
            [
              {
                field: "document_number",
                code: "EXISTING_CLIENT",
                message: "Usa el cliente existente.",
                resource_id: "cl-9",
              },
            ],
          ),
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });
    await fillRequired(user);
    await submit(user);

    const number = screen.getByRole("textbox", { name: "Número de documento" });
    await waitFor(() =>
      expect(number).toHaveAccessibleDescription(
        "Ya existe un cliente con ese tipo y número de documento.",
      ),
    );
    expect(screen.getByRole("link", { name: "Ver el cliente existente" })).toHaveAttribute(
      "href",
      "/clientes/cl-9",
    );
    expect(nav.push).not.toHaveBeenCalled();

    // Cambiar el tipo de documento quita el enlace.
    await pick(user, "Tipo de documento", "Cédula de extranjería");
    expect(
      screen.queryByRole("link", { name: "Ver el cliente existente" }),
    ).not.toBeInTheDocument();
  });

  it("si el duplicado no es visible, el error va al campo sin enlace", async () => {
    useBaseApi();
    server.use(
      http.post(apiUrl("/clients"), () =>
        HttpResponse.json(apiError("DUPLICATE_CLIENT_DOCUMENT", "Ya existe un cliente."), {
          status: 409,
        }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });
    await fillRequired(user);
    await submit(user);

    expect(await screen.findByText("Ya existe un cliente.")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Ver el cliente existente" }),
    ).not.toBeInTheDocument();
  });

  it("los errores de validación de la API van a su campo y el resto al aviso", async () => {
    useBaseApi();
    server.use(
      http.post(apiUrl("/clients"), () =>
        HttpResponse.json(
          apiError("VALIDATION_ERROR", "Revisa los datos.", [
            {
              field: "document_number",
              code: "invalid",
              message: "Número de documento no válido para CC: usa solo dígitos.",
            },
            { field: null, code: "other", message: "Algo general." },
          ]),
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });
    await fillRequired(user);
    await submit(user);

    expect(
      await screen.findByText("Número de documento no válido para CC: usa solo dígitos."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Revisa los datos.")).toBeInTheDocument();
    expect(screen.getByText("Algo general.")).toBeInTheDocument();
  });

  it("sin permiso de crear lo dice", async () => {
    useBaseApi({ ...CLIENTS_ME, permissions: ["clients.read"] });
    renderWithProviders(<NewClientScreen />);
    expect(await screen.findByText("No tienes permiso para crear clientes")).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("'Cancelar' vuelve al listado", async () => {
    useBaseApi();
    const user = userEvent.setup();
    renderWithProviders(<NewClientScreen />);
    await screen.findByRole("heading", { name: "Nuevo cliente" });
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(nav.push).toHaveBeenCalledWith("/clientes");
  });
});

describe("editar cliente", { timeout: 20_000 }, () => {
  function useClientApi(detail = makeClientDetail()) {
    useBaseApi();
    const patches: unknown[] = [];
    server.use(
      http.get(apiUrl("/clients/cl-1"), () => HttpResponse.json(detail)),
      http.patch(apiUrl("/clients/cl-1"), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patches.push(body);
        return HttpResponse.json({ ...detail, ...body });
      }),
    );
    return patches;
  }

  it("carga los datos y manda solo lo cambiado", async () => {
    const patches = useClientApi();
    const user = userEvent.setup();
    renderWithProviders(<EditClientScreen id="cl-1" />);

    const phone = await screen.findByRole("textbox", { name: /Teléfono/ });
    expect(phone).toHaveValue("+573104458821");
    expect(screen.getByRole("textbox", { name: "Nombres" })).toHaveValue("Laura");
    const save = screen.getByRole("button", { name: "Guardar cambios" });
    expect(save).toBeDisabled();

    await user.clear(phone);
    await user.type(phone, "+573001112233");
    await user.click(save);

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/clientes/cl-1"));
    expect(patches).toEqual([{ phone: "+573001112233" }]);
    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
  });

  it("vaciar el origen lo borra", async () => {
    const patches = useClientApi();
    const user = userEvent.setup();
    renderWithProviders(<EditClientScreen id="cl-1" />);
    const origin = await screen.findByRole("combobox", { name: /Origen/ });
    const select = origin.closest<HTMLElement>(".ant-select")!;
    expect(await within(select).findByText("Directo")).toBeInTheDocument();
    await user.click(select.querySelector(".ant-select-clear")!);
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(patches).toEqual([{ origin_type: null }]));
  });

  it("un origen que ya no está activo se ve con su etiqueta", async () => {
    useClientApi(makeClientDetail({ origin: { code: "RETIRED", label: "Origen retirado" } }));
    renderWithProviders(<EditClientScreen id="cl-1" />);
    const origin = await screen.findByRole("combobox", { name: /Origen/ });
    const select = origin.closest<HTMLElement>(".ant-select")!;
    expect(within(select).getByText("Origen retirado")).toBeInTheDocument();
  });

  it("un cliente que no existe muestra 'No encontramos'", async () => {
    useBaseApi();
    server.use(
      http.get(apiUrl("/clients/cl-x"), () =>
        HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 }),
      ),
    );
    renderWithProviders(<EditClientScreen id="cl-x" />);
    expect(
      await screen.findByText("No encontramos este cliente o no tienes acceso"),
    ).toBeInTheDocument();
  });

  it("sin permiso de editar lo dice", async () => {
    useBaseApi({ ...CLIENTS_ME, permissions: ["clients.read"] });
    renderWithProviders(<EditClientScreen id="cl-1" />);
    expect(await screen.findByText("No tienes permiso para editar clientes")).toBeInTheDocument();
  });
});

describe("detalle del cliente", { timeout: 20_000 }, () => {
  it("muestra el encabezado y los datos, con 'Editar'", async () => {
    useBaseApi();
    server.use(http.get(apiUrl("/clients/cl-1"), () => HttpResponse.json(makeClientDetail())));
    const user = userEvent.setup();
    renderWithProviders(<ClientDetailScreen id="cl-1" />);

    expect(await screen.findByRole("heading", { name: "Laura Gómez Vélez" })).toBeInTheDocument();
    expect(screen.getByText("Origen: Directo")).toBeInTheDocument();
    expect(screen.getByText("12 abr 1990")).toBeInTheDocument();
    expect(screen.getByText("Cédula de ciudadanía 1032445908")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Editar" }));
    expect(nav.push).toHaveBeenCalledWith("/clientes/cl-1/editar");
  });

  it("un error muestra 'Reintentar'", async () => {
    useBaseApi();
    let fail = true;
    server.use(
      http.get(apiUrl("/clients/cl-1"), () =>
        fail
          ? HttpResponse.json(apiError("PERMISSION_DENIED", "Sin permiso."), { status: 403 })
          : HttpResponse.json(makeClientDetail()),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<ClientDetailScreen id="cl-1" />);
    expect(await screen.findByText("No pudimos cargar el cliente")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { name: "Laura Gómez Vélez" })).toBeInTheDocument();
  });
});
