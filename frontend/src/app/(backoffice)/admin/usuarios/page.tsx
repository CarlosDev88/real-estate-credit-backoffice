import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminUsersScreen } from "@/features/admin-users/admin-users-screen";

export const metadata: Metadata = { title: "Usuarios" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function AdminUsuariosPage() {
  return (
    <Suspense>
      <AdminUsersScreen />
    </Suspense>
  );
}
