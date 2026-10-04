import type { Metadata } from "next";
import { DriverInvitationLanding } from "@/components/auth/driver-invitation-landing";

export const metadata: Metadata = { title: "Invitación de conductor | Amira" };

export default function DriverInvitationPage() {
  return <DriverInvitationLanding />;
}
