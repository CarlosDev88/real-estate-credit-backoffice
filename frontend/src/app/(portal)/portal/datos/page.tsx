import type { Metadata } from "next";

import { ProfileScreen } from "@/features/buyer-portal/forms/profile-screen";

export const metadata: Metadata = { title: "Tus datos personales" };

export default function Page() {
  return <ProfileScreen />;
}
