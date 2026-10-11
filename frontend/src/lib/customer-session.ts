import { createClient } from "@/lib/supabase/client";

export class CustomerSessionError extends Error {}

// Confirms the signed-in account can use customer features and returns its user id.
export async function readCustomerUserId(): Promise<string> {
  const client = createClient();
  const { data: userData, error: userError } = await client.auth.getUser();
  if (userError || !userData.user?.email_confirmed_at) throw new CustomerSessionError();
  const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if (assuranceError || assurance.currentLevel !== "aal2") throw new CustomerSessionError();
  return userData.user.id;
}

// Read per request: supabase-js returns a current token and refreshes it when expired.
export async function readAccessToken(): Promise<string> {
  const { data, error } = await createClient().auth.getSession();
  if (error || !data.session?.access_token) throw new CustomerSessionError();
  return data.session.access_token;
}

// getSession can keep returning a token the server has rejected, so a 401 forces a refresh.
export async function refreshAccessToken(): Promise<string> {
  const { data, error } = await createClient().auth.refreshSession();
  if (error || !data.session?.access_token) throw new CustomerSessionError();
  return data.session.access_token;
}
