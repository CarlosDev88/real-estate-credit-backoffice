import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ComponentsPreview } from "./components-preview";

export const metadata: Metadata = { title: "Componentes compartidos" };

// Demo de components/ui: solo existe en desarrollo.
export default function DevComponentsPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <ComponentsPreview />;
}
