import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIdlePreload, useMountedOnce } from "@/lib/hooks/use-lazy";

describe("useMountedOnce", () => {
  it("es false hasta la primera apertura y queda true al cerrar", () => {
    const { result, rerender } = renderHook(({ open }) => useMountedOnce(open), {
      initialProps: { open: false },
    });
    expect(result.current).toBe(false);
    rerender({ open: true });
    expect(result.current).toBe(true);
    rerender({ open: false });
    expect(result.current).toBe(true);
  });
});

describe("useIdlePreload", () => {
  afterEach(() => vi.useRealTimers());

  it("precarga después de la espera y no antes; nada si está apagado", async () => {
    vi.useFakeTimers();
    const load = vi.fn(() => Promise.resolve());
    const off = vi.fn(() => Promise.resolve());
    renderHook(() => {
      useIdlePreload([load]);
      useIdlePreload([off], false);
    });
    expect(load).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(load).toHaveBeenCalledTimes(1);
    expect(off).not.toHaveBeenCalled();
  });
});
