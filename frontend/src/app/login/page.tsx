import type { Metadata } from "next";
import { AuthPanel } from "@/components/auth/auth-panel";

export const metadata: Metadata = { title: "Iniciar sesión | Amira" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const params = await searchParams;
  return <AuthPanel mode="login" invitationIntent={params.next === "/invitacion/conductor/aceptar"} />;
}
