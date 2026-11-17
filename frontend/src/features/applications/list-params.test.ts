import { describe, expect, it } from "vitest";

import {
  compact,
  filtersOf,
  formatOrdering,
  parseListParams,
  parseOrdering,
  serializeListParams,
} from "@/features/applications/list-params";

describe("estado del listado en la URL", () => {
  it("sin parámetros usa los valores por defecto", () => {
    expect(parseListParams(new URLSearchParams())).toEqual({
      quick_filter: "all",
      search: "",
      bank_id: "",
      product_type: "",
      purpose: "",
      ordering: "-updated_at",
      page: 1,
      page_size: 20,
    });
  });

  it("descarta valores inválidos de orden, página y tamaño", () => {
    const params = parseListParams(
      new URLSearchParams("ordering=-status&page=0&page_size=33&search=%20ana%20"),
    );
    expect(params).toMatchObject({
      ordering: "-updated_at",
      page: 1,
      page_size: 20,
      search: "ana",
    });
    expect(parseListParams(new URLSearchParams("page=abc")).page).toBe(1);
  });

  it("ida y vuelta sin escribir los valores por defecto", () => {
    const params = parseListParams(
      new URLSearchParams(
        "quick_filter=review&search=ana&bank_id=b1&product_type=MORTGAGE&purpose=NEW&ordering=code&page=2&page_size=50",
      ),
    );
    const qs = serializeListParams(params);
    expect(qs).toBe(
      "quick_filter=review&search=ana&bank_id=b1&product_type=MORTGAGE&purpose=NEW&ordering=code&page=2&page_size=50",
    );
    expect(parseListParams(new URLSearchParams(qs))).toEqual(params);
    expect(serializeListParams(parseListParams(new URLSearchParams()))).toBe("");
  });

  it("orden: signo menos es descendente", () => {
    expect(parseOrdering("-requested_amount")).toEqual({ field: "requested_amount", desc: true });
    expect(parseOrdering("bank_name")).toEqual({ field: "bank_name", desc: false });
    expect(formatOrdering({ field: "code", desc: true })).toBe("-code");
  });

  it("los filtros de las pestañas no llevan pestaña, orden ni página, y se compactan", () => {
    const params = parseListParams(new URLSearchParams("quick_filter=ready&purpose=NEW&page=3"));
    expect(filtersOf(params)).toEqual({
      search: "",
      bank_id: "",
      product_type: "",
      purpose: "NEW",
    });
    expect(compact(filtersOf(params))).toEqual({ purpose: "NEW" });
  });
});
