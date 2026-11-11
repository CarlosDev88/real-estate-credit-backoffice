import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ShellPreview } from "./shell-preview";

export const metadata: Metadata = { title: "Shell" };

// Demo del AppShell: solo existe en desarrollo.
export default function DevShellPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <ShellPreview />;
}
