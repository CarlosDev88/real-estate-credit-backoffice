import type { Metadata } from "next";

import { AcceptInvitationScreen } from "@/features/admin-users/accept-invitation-screen";

// La ruta es la del correo de invitación (`INVITATION_ACCEPT_URL` del backend).
// Sin `Referer`: el token nunca sale hacia otro sitio.
export const metadata: Metadata = { title: "Aceptar invitación", referrer: "no-referrer" };

export default function AceptarInvitacionPage() {
  return <AcceptInvitationScreen />;
}
