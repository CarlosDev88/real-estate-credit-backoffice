import type { Metadata } from "next";

import { FinancingScreen } from "@/features/buyer-portal/forms/financing-screen";

export const metadata: Metadata = { title: "Financiación" };

export default function Page() {
  return <FinancingScreen />;
}
