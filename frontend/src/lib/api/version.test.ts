import { describe, expect, it } from "vitest";

import { ifMatch, parseVersion, versionOf } from "@/lib/api/version";

describe("parseVersion", () => {
  it.each([
    ['"7"', 7],
    ["7", 7],
    ['W/"7"', 7],
    [7, 7],
    [' "12" ', 12],
  ] as const)("lee %s", (input, expected) => {
    expect(parseVersion(input)).toBe(expected);
  });

  it.each([null, undefined, "", "abc", '"7', -1, 1.5])("rechaza %s", (input) => {
    expect(parseVersion(input)).toBeNull();
  });
});

describe("ifMatch", () => {
  it('normaliza a "7"', () => {
    expect(ifMatch(7)).toBe('"7"');
    expect(ifMatch("7")).toBe('"7"');
    expect(ifMatch('W/"7"')).toBe('"7"');
  });

  it("falla con una versión inválida", () => {
    expect(() => ifMatch("x")).toThrow(/inválida/);
  });
});

describe("versionOf", () => {
  it("lee el ETag también de un 204", () => {
    expect(versionOf(new Response(null, { status: 204, headers: { ETag: '"8"' } }))).toBe(8);
    expect(versionOf(new Response(null, { status: 204 }))).toBeNull();
  });
});
