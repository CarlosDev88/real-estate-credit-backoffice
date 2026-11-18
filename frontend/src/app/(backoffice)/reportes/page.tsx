import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportsScreen } from "@/features/reports/reports-screen";

export const metadata: Metadata = { title: "Reportes" };

// La pestaña y los filtros viven en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function ReportesPage() {
  return (
    <Suspense>
      <ReportsScreen />
    </Suspense>
  );
}
