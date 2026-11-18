import type { Metadata } from "next";

import { NewClientScreen } from "@/features/clients/client-screens";

export const metadata: Metadata = { title: "Nuevo cliente" };

export default function NuevoClientePage() {
  return <NewClientScreen />;
}
