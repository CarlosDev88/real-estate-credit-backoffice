import type { Metadata } from "next";

import { BuyerDocumentsScreen } from "@/features/buyer-documents/documents-screen";

export const metadata: Metadata = { title: "Tus documentos" };

export default function DocumentosPage() {
  return <BuyerDocumentsScreen />;
}
