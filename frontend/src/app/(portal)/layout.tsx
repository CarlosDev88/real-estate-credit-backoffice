import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PortalGuard } from "@/features/buyer-portal/portal-guard";

export const metadata: Metadata = { title: { default: "Tu solicitud", template: "%s · Umbral" } };

export default function PortalLayout({ children }: { children: ReactNode }) {
  return <PortalGuard>{children}</PortalGuard>;
}
