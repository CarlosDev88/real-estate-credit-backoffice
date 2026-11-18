import type { Metadata } from "next";

import { ConsentsScreen } from "@/features/buyer-portal/consents-screen";

export const metadata: Metadata = { title: "Consentimientos" };

export default function ConsentimientosPage() {
  return <ConsentsScreen />;
}
