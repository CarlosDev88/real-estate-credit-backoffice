import type { Metadata } from "next";

import { ClientDetailScreen } from "@/features/clients/client-detail-screen";

export const metadata: Metadata = { title: "Cliente" };

export default async function ClientePage({ params }: PageProps<"/clientes/[id]">) {
  const { id } = await params;
  return <ClientDetailScreen id={id} />;
}
