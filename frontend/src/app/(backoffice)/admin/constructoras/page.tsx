import type { Metadata } from "next";
import { Suspense } from "react";

import { PartnersScreen } from "@/features/admin-partners/partners-screen";

export const metadata: Metadata = { title: "Constructoras" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function AdminConstructorasPage() {
  return (
    <Suspense>
      <PartnersScreen />
    </Suspense>
  );
}
