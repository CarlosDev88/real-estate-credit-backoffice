import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { UiPreview } from "./ui-preview";

export const metadata: Metadata = { title: "Componentes" };

// Página de revisión de componentes: solo existe en desarrollo.
export default function DevUiPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <UiPreview />;
}
