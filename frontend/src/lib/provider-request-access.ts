import { acceptsAssuranceLevel } from "@/lib/auth/dev-mfa";
import { createClient } from "@/lib/supabase/client";

export type ProviderAccessReason = "sign-in" | "aal2" | "session";

export class ProviderRequestAccessError extends Error {
  constructor(readonly reason: ProviderAccessReason) {
    super(reason);
    this.name = "ProviderRequestAccessError";
  }
}

// Returns the access token of a confirmed, MFA-satisfied session or throws a typed access error.
export async function currentAccessToken(): Promise<string> {
  const client = createClient();
  const { data: userData, error: userError } = await client.auth.getUser();
  if (userError || !userData.user?.email_confirmed_at) throw new ProviderRequestAccessError("sign-in");
  const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if (assuranceError) throw assuranceError;
  if (!acceptsAssuranceLevel(assurance.currentLevel)) throw new ProviderRequestAccessError("aal2");
  const { data, error } = await client.auth.getSession();
  if (error || !data.session?.access_token) throw new ProviderRequestAccessError("session");
  return data.session.access_token;
}

export function isSignInRequired(cause: unknown): boolean {
  return cause instanceof ProviderRequestAccessError;
}

export function paymentAccessMessage(reason: ProviderAccessReason): string {
  if (reason === "sign-in") return "Inicia sesión con tu correo confirmado para ver tu pago.";
  if (reason === "aal2") return "Verifica tu teléfono por SMS para ver tu pago.";
  return "Tu sesión expiró. Inicia sesión nuevamente para continuar.";
}

export function requestErrorMessage(cause: unknown): string {
  if (cause instanceof ProviderRequestAccessError) {
    if (cause.reason === "sign-in") return "Inicia sesión con tu correo confirmado para ver las solicitudes.";
    if (cause.reason === "aal2") return "Verifica tu teléfono por SMS para administrar solicitudes.";
    return "Tu sesión expiró. Inicia sesión nuevamente para continuar.";
  }
  if (cause instanceof Error && /API todavía no está configurada/i.test(cause.message)) return cause.message;
  return "No pudimos cargar las solicitudes. Inténtalo nuevamente.";
}
