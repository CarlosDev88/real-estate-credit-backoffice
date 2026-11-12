import type { ReactNode } from "react";

import { BackofficeGuard } from "@/features/auth/backoffice-guard";

export default function BackofficeLayout({ children }: { children: ReactNode }) {
  return <BackofficeGuard>{children}</BackofficeGuard>;
}
