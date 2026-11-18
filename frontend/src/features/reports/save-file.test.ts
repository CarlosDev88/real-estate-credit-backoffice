import { afterEach, describe, expect, it, vi } from "vitest";

import { saveBlob } from "@/features/reports/save-file";

describe("saveBlob", () => {
  afterEach(() => vi.useRealTimers());

  it("descarga el archivo con su nombre y libera la URL", () => {
    vi.useFakeTimers();
    const create = vi.fn(() => "blob:reporte");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe("solicitudes.csv");
      expect(this.getAttribute("href")).toBe("blob:reporte");
    });

    saveBlob(new Blob(["a"]), "solicitudes.csv");
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector("a[download]")).toBeNull();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith("blob:reporte");
  });
});
