import type { Metadata } from "next";

import { CatalogScreen } from "@/features/admin-catalogs/catalog-screen";

export const metadata: Metadata = { title: "Catálogo" };

export default async function AdminCatalogoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CatalogScreen catalogId={id} />;
}
