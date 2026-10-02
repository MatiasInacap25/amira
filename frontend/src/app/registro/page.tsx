import type { Metadata } from "next";
import { AuthPanel } from "@/components/auth/auth-panel";

export const metadata: Metadata = { title: "Crear cuenta | Amira" };

export default async function RegisterPage({ searchParams }: { searchParams: Promise<{ intent?: string }> }) {
  const params = await searchParams;
  return <AuthPanel mode="register" providerIntent={params.intent === "provider"} />;
}
