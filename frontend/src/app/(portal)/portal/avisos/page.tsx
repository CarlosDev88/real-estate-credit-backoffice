import type { Metadata } from "next";

import { BuyerNotificationsScreen } from "@/features/buyer-notifications/notifications-screen";

export const metadata: Metadata = { title: "Tus avisos" };

export default function AvisosPage() {
  return <BuyerNotificationsScreen />;
}
