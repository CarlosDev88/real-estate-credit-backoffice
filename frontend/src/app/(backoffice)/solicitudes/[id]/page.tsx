import type { Metadata } from "next";
import { Suspense } from "react";

import { WorkspaceScreen } from "@/features/applications/workspace-screen";

export const metadata: Metadata = { title: "Solicitud" };

// La pestaña activa vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default async function SolicitudPage({ params }: PageProps<"/solicitudes/[id]">) {
  const { id } = await params;
  return (
    <Suspense>
      <WorkspaceScreen id={id} />
    </Suspense>
  );
}
