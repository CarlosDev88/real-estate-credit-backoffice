import type { Metadata } from "next";
import { Suspense } from "react";

import { WorkflowScreen } from "@/features/admin-workflow/workflow-screen";

export const metadata: Metadata = { title: "Flujos" };

// El flujo, los filtros y la transición abierta viven en la URL (`useSearchParams`).
export default function AdminFlujosPage() {
  return (
    <Suspense>
      <WorkflowScreen />
    </Suspense>
  );
}
