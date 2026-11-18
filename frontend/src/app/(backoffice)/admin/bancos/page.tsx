import type { Metadata } from "next";
import { Suspense } from "react";

import { BanksScreen } from "@/features/admin-banks/banks-screen";

export const metadata: Metadata = { title: "Bancos" };

// El estado del listado vive en la URL (`useSearchParams`): va dentro de `Suspense`.
export default function AdminBancosPage() {
  return (
    <Suspense>
      <BanksScreen />
    </Suspense>
  );
}
