import type { Metadata } from "next";
import { AuthPanel } from "@/components/auth/auth-panel";

export const metadata: Metadata = { title: "Crear cuenta | Amira" };

export default function RegisterPage() {
  return <AuthPanel mode="register" />;
}
