import type { Metadata } from "next";

import { PropertyScreen } from "@/features/buyer-portal/forms/property-screen";

export const metadata: Metadata = { title: "El inmueble" };

export default function Page() {
  return <PropertyScreen />;
}
