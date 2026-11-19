import type { Metadata } from "next";
import { Suspense } from "react";

import { BrokerScreen } from "@/features/broker/broker-screen";

export const metadata: Metadata = { title: "Mis prospectos" };

// La pestaña, el estado y la página viven en la URL (`useSearchParams`).
export default function ProspectosPage() {
  return (
    <Suspense>
      <BrokerScreen />
    </Suspense>
  );
}
