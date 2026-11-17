import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/test/msw-server";

// El primer render de un expediente (Ant Design en frío, varias consultas MSW) pasa del
// segundo por defecto cuando la suite corre en paralelo: `findBy*` y `waitFor` esperan 5 s.
configure({ asyncUtilTimeout: 5000 });

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
