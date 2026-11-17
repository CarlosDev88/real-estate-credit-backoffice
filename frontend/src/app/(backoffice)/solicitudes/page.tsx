import type { Metadata } from "next";
import { Suspense } from "react";

import { ApplicationsListScreen } from "@/features/applications/applications-list-screen";

export const metadata: Metadata = { title: "Solicitudes" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function SolicitudesPage() {
  return (
    <Suspense>
      <ApplicationsListScreen />
    </Suspense>
  );
}
