import type { Metadata } from "next";
import { Suspense } from "react";

import { CommissionsScreen } from "@/features/commissions/commissions-screen";

export const metadata: Metadata = { title: "Comisiones" };

// La pestaña, los filtros y el detalle abierto viven en la URL (`useSearchParams`).
export default function ComisionesPage() {
  return (
    <Suspense>
      <CommissionsScreen />
    </Suspense>
  );
}
