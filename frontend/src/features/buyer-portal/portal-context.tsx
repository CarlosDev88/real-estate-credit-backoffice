"use client";

import { createContext, useContext } from "react";

import type { BuyerSession } from "@/features/buyer-portal/queries";

export interface PortalContextValue {
  session: BuyerSession;
  applicationId: string;
  /** La solicitud está cerrada o no admite cambios: los formularios van en solo lectura. */
  readOnly: boolean;
  /** Un `409` de solo lectura (`isReadOnlyError`): vuelve a pedir la sesión para pintar la franja. */
  refreshSession: () => Promise<void>;
}

const PortalContext = createContext<PortalContextValue | null>(null);

export const PortalProvider = PortalContext.Provider;

/** Sesión del portal. Solo existe dentro del layout de `(portal)`. */
export function usePortal(): PortalContextValue {
  const value = useContext(PortalContext);
  if (!value) throw new Error("usePortal se usa dentro del layout del portal.");
  return value;
}
