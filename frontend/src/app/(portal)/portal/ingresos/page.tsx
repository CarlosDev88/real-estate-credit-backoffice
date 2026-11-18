import type { Metadata } from "next";

import { IncomeScreen } from "@/features/buyer-portal/forms/income-screen";

export const metadata: Metadata = { title: "Ingresos y gastos" };

export default function Page() {
  return <IncomeScreen />;
}
