import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentsScreen } from "@/features/admin-documents/documents-screen";

export const metadata: Metadata = { title: "Documentos" };

// El estado de las pestañas y los listados vive en la URL (`useSearchParams`).
export default function AdminDocumentosPage() {
  return (
    <Suspense>
      <DocumentsScreen />
    </Suspense>
  );
}
