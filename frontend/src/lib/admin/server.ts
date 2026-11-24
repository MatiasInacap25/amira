import { redirect } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import { createClient } from "@/lib/supabase/server";

type AdminIdentity = { user_id: string; email: string };

export const checkAdmin = cache(async (): Promise<{ admin: AdminIdentity; accessToken: string } | null> => {
  await connection();
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) redirect("/login?next=/admin");

  // The session cookie supplies the bearer token only; FastAPI verifies the token and decides access.
  const response = await authenticatedApiFetch("/api/admin/me", token, process.env.NEXT_PUBLIC_API_URL);
  if (response.status === 401) redirect("/login?next=/admin");
  if (response.status === 403) return null;
  if (!response.ok) throw new Error("Admin authorization is unavailable.");
  return { admin: await response.json() as AdminIdentity, accessToken: token };
});

export function serverAdminFetch(path: `/api/admin/${string}`, accessToken: string) {
  return authenticatedApiFetch(path, accessToken, process.env.NEXT_PUBLIC_API_URL);
}

export async function adminData<T>(path: `/api/admin/${string}`, accessToken: string): Promise<T | null> {
  try {
    const response = await serverAdminFetch(path, accessToken);
    return response.ok ? await response.json() as T : null;
  } catch {
    return null;
  }
}
