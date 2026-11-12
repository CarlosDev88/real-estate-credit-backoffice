import { render, type RenderOptions } from "@testing-library/react";
import { App } from "antd";
import type { ReactElement, ReactNode } from "react";

import { makeQueryClient } from "@/providers/query-provider";
import { QueryClientProvider } from "@tanstack/react-query";

/** Render con Query (cliente nuevo por prueba) y el `App` de Ant Design. */
export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const client = makeQueryClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <App>{children}</App>
    </QueryClientProvider>
  );
  return { client, ...render(ui, { wrapper: Wrapper, ...options }) };
}
