import type { Metadata } from "next";
import { Suspense } from "react";

import { ProductScreen } from "@/features/admin-banks/product-screen";

export const metadata: Metadata = { title: "Producto bancario" };

// Las reglas del producto guardan sus filtros en la URL (`useSearchParams`).
export default async function AdminProductoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <ProductScreen productId={id} />
    </Suspense>
  );
}
