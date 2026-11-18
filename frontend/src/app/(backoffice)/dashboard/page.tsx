import type { Metadata } from "next";
import { Suspense } from "react";

import { DashboardScreen } from "@/features/dashboard/dashboard-screen";

export const metadata: Metadata = { title: "Dashboard" };

// Los filtros viven en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardScreen />
    </Suspense>
  );
}
