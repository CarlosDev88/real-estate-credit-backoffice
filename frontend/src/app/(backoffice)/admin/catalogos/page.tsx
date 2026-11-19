import type { Metadata } from "next";
import { Suspense } from "react";

import { CatalogsScreen } from "@/features/admin-catalogs/catalogs-screen";

export const metadata: Metadata = { title: "Catálogos" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function AdminCatalogosPage() {
  return (
    <Suspense>
      <CatalogsScreen />
    </Suspense>
  );
}
