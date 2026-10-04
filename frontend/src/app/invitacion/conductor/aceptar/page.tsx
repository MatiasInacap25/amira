import type { Metadata } from "next";
import { AcceptDriverInvitation } from "@/components/auth/accept-driver-invitation";

export const metadata: Metadata = { title: "Aceptar invitación | Amira" };

export default function AcceptDriverInvitationPage() {
  return <AcceptDriverInvitation />;
}
