import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/test/msw-server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(() => {
  server.resetHandlers();
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
