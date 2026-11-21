import type { Metadata } from "next";

import { AcceptInvitationScreen } from "@/features/admin-users/accept-invitation-screen";

// La ruta es la del correo de invitación (`INVITATION_ACCEPT_URL` del backend).
// Sin `Referer`: el token nunca sale hacia otro sitio.
export const metadata: Metadata = { title: "Aceptar invitación", referrer: "no-referrer" };

export default async function AceptarInvitacionPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // Solo si hay token: el token mismo no se usa en el servidor (lo lee y lo quita el cliente).
  const { token } = await searchParams;
  return <AcceptInvitationScreen hasToken={typeof token === "string" && token.trim() !== ""} />;
}
