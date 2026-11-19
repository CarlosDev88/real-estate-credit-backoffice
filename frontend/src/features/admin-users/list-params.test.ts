import { describe, expect, it } from "vitest";

import {
  compact,
  formatOrdering,
  parseOrdering,
  serializeListParams,
} from "@/features/admin-common/list-params";
import { optionLabel } from "@/features/admin-common/list-filters";
import {
  ADMIN_USERS_CONFIG,
  ADMIN_USERS_DEFAULTS,
  parseAdminUsersParams,
} from "@/features/admin-users/list-params";
import { INVITATION_STATUSES, statusOf, USER_STATUSES } from "@/features/admin-users/status";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const parse = (qs: string) => parseAdminUsersParams(new URLSearchParams(qs));

describe("parámetros de /admin/usuarios", () => {
  it("sin nada en la URL, los valores por defecto", () => {
    expect(parse("")).toEqual(ADMIN_USERS_DEFAULTS);
    expect(serializeListParams(ADMIN_USERS_DEFAULTS, ADMIN_USERS_CONFIG)).toBe("");
  });

  it("lee los filtros de usuarios y descarta los inválidos", () => {
    expect(
      parse(
        `search=%20ana%20&role=ADVISOR&status=INACTIVE&ordering=last_login&page=2&page_size=50&usuario=${USER_ID}`,
      ),
    ).toEqual({
      vista: "usuarios",
      search: "ana",
      role: "ADVISOR",
      status: "INACTIVE",
      ordering: "last_login",
      page: 2,
      page_size: 50,
      usuario: USER_ID,
    });
    expect(
      parse("role=bad role&status=REVOKED&ordering=-expires_at&page=0&page_size=7&usuario=x"),
    ).toEqual(ADMIN_USERS_DEFAULTS);
  });

  it("en invitaciones, sus estados y su orden; sin búsqueda ni panel", () => {
    expect(
      parse(`vista=invitaciones&search=ana&status=REVOKED&ordering=-expires_at&usuario=${USER_ID}`),
    ).toMatchObject({
      vista: "invitaciones",
      search: "",
      status: "REVOKED",
      ordering: "-expires_at",
      usuario: "",
    });
    expect(parse("vista=invitaciones&status=INACTIVE&ordering=last_login")).toMatchObject({
      status: "",
      ordering: "-created_at",
    });
  });

  it("escribe solo lo que no es por defecto, en un orden fijo", () => {
    expect(
      serializeListParams(
        { ...ADMIN_USERS_DEFAULTS, usuario: USER_ID, status: "ACTIVE", vista: "usuarios" },
        ADMIN_USERS_CONFIG,
      ),
    ).toBe(`status=ACTIVE&usuario=${USER_ID}`);
    expect(
      serializeListParams({ ...ADMIN_USERS_DEFAULTS, vista: "invitaciones" }, ADMIN_USERS_CONFIG),
    ).toBe("vista=invitaciones");
  });
});

describe("ayudas comunes", () => {
  it("orden: campo desconocido → el por defecto", () => {
    expect(parseOrdering("-email", ["email"], "-created_at")).toEqual({
      field: "email",
      desc: true,
    });
    expect(parseOrdering("phone", ["email"], "created_at")).toEqual({
      field: "created_at",
      desc: false,
    });
    expect(formatOrdering({ field: "email", desc: true })).toBe("-email");
  });

  it("compact quita lo vacío", () => {
    expect(compact({ a: "", b: "x", c: undefined, d: 0 })).toEqual({ b: "x", d: 0 });
  });

  it("etiqueta del filtro: todos, la de la opción o …", () => {
    const options = [{ value: "A", label: "Uno" }];
    expect(optionLabel(options, "")).toBe("todos");
    expect(optionLabel(options, "A")).toBe("Uno");
    expect(optionLabel(options, "B")).toBe("…");
  });

  it("estados: etiqueta y tono; uno desconocido, neutro y con su código", () => {
    expect(statusOf(USER_STATUSES, "ACTIVE")).toMatchObject({ label: "Activo", tone: "success" });
    expect(statusOf(INVITATION_STATUSES, "EXPIRED").tone).toBe("neutral");
    expect(statusOf(USER_STATUSES, "NEW")).toEqual({ value: "NEW", label: "NEW", tone: "neutral" });
  });
});
