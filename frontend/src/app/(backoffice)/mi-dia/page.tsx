import type { Metadata } from "next";
import { Suspense } from "react";

import { MyDayScreen } from "@/features/workday/my-day-screen";

export const metadata: Metadata = { title: "Mi día" };

// La pestaña y los filtros viven en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function MiDiaPage() {
  return (
    <Suspense>
      <MyDayScreen />
    </Suspense>
  );
}
