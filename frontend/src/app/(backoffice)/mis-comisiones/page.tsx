import type { Metadata } from "next";
import { Suspense } from "react";

import { MyCommissionsScreen } from "@/features/commissions/my-commissions-screen";

export const metadata: Metadata = { title: "Mis comisiones" };

// Los filtros y la página viven en la URL (`useSearchParams`).
export default function MisComisionesPage() {
  return (
    <Suspense>
      <MyCommissionsScreen />
    </Suspense>
  );
}
