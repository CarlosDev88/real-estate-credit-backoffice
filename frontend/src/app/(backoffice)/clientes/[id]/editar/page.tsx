import type { Metadata } from "next";

import { EditClientScreen } from "@/features/clients/client-screens";

export const metadata: Metadata = { title: "Editar cliente" };

export default async function EditarClientePage({ params }: PageProps<"/clientes/[id]/editar">) {
  const { id } = await params;
  return <EditClientScreen id={id} />;
}
