import { describe, expect, it } from "vitest";

import {
  contextSkeleton,
  describeCondition,
  fieldsOf,
  parseJson,
  pretty,
} from "@/features/admin-banks/condition";

const CONDITION = {
  operator: "and",
  conditions: [
    { operator: "lte", left: { field: "financing.term_months" }, right: 360 },
    {
      operator: "or",
      conditions: [
        { operator: "in", left: { field: "property.property_type_code" }, right: ["HOUSE", "APT"] },
        { operator: "eq", left: { field: "property.has_project" }, right: true },
      ],
    },
    {
      operator: "gte",
      left: {
        operator: "ratio",
        numerator_field: "household.monthly_income_cop",
        denominator_field: "financing.requested_amount_cop",
      },
      right: 0.01,
    },
    {
      operator: "gte",
      left: {
        operator: "sum",
        fields: ["financing.own_resources_cop", "financing.severance_funds_cop"],
      },
      right: 1000000,
    },
  ],
};

describe("condiciones de reglas", () => {
  it("resume la condición en texto", () => {
    expect(describeCondition(CONDITION)).toBe(
      "financing.term_months ≤ 360 y " +
        '(property.property_type_code en ["HOUSE", "APT"] o property.has_project = sí) y ' +
        "(household.monthly_income_cop / financing.requested_amount_cop) ≥ 0,01 y " +
        "(financing.own_resources_cop + financing.severance_funds_cop) ≥ 1.000.000",
    );
    expect(describeCondition({ operator: "nope" })).toBe('{"operator":"nope"}');
    expect(describeCondition("texto")).toBe('"texto"');
  });

  it("encuentra los campos y arma un contexto de ejemplo", () => {
    expect(fieldsOf(CONDITION)).toEqual([
      "financing.term_months",
      "property.property_type_code",
      "property.has_project",
      "household.monthly_income_cop",
      "financing.requested_amount_cop",
      "financing.own_resources_cop",
      "financing.severance_funds_cop",
    ]);
    expect(contextSkeleton(CONDITION)).toEqual({
      financing: {
        term_months: null,
        requested_amount_cop: null,
        own_resources_cop: null,
        severance_funds_cop: null,
      },
      property: { property_type_code: null, has_project: null },
      household: { monthly_income_cop: null },
    });
  });

  it("JSON: lee y formatea", () => {
    expect(parseJson('{"a": 1}')).toEqual({ ok: true, value: { a: 1 } });
    expect(parseJson("{a")).toEqual({ ok: false });
    expect(pretty({ a: 1 })).toBe('{\n  "a": 1\n}');
  });
});
