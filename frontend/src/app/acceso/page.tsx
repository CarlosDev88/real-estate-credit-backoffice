import type { Metadata } from "next";

import { AccessScreen } from "@/features/buyer-portal/access-screen";

export const metadata: Metadata = { title: "Acceso", referrer: "no-referrer" };

export default function AccesoPage() {
  return <AccessScreen />;
}
