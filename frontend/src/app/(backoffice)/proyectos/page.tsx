import type { Metadata } from "next";
import { Suspense } from "react";

import { ProjectsScreen } from "@/features/admin-projects/projects-screen";

export const metadata: Metadata = { title: "Proyectos" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function ProyectosPage() {
  return (
    <Suspense>
      <ProjectsScreen />
    </Suspense>
  );
}
