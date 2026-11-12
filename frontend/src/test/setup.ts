import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/test/msw-server";

// Algunas pruebas (proxy.ts) corren en entorno Node, sin DOM.
const hasDom = typeof window !== "undefined";

if (hasDom) {
  // jsdom no trae matchMedia; Ant Design y useMediaQuery lo usan.
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList;
  }
  // Ni ResizeObserver (lo usan el menú de Ant Design y ScrollTabs).
  if (typeof window.ResizeObserver === "undefined") {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
}

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(() => {
  server.resetHandlers();
  if (!hasDom) return;
  cleanup();
  try {
    window.localStorage.clear();
  } catch {
    // algunas pruebas simulan un localStorage que falla
  }
  for (const part of document.cookie.split("; ")) {
    const name = part.split("=")[0];
    if (name) document.cookie = `${name}=; Max-Age=0; Path=/`;
  }
  window.history.replaceState(null, "", "/");
});

afterAll(() => server.close());
