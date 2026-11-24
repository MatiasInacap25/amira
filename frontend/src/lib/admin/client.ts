import { authenticatedApiFetch } from "@/lib/auth/account-api";
import { createClient } from "@/lib/supabase/client";

export async function adminRequest(path: `/api/admin/${string}`, options?: RequestInit) {
  const { data } = await createClient().auth.getSession();
  if (!data.session) throw new Error("Tu sesión ha expirado.");
  return authenticatedApiFetch(path, data.session.access_token, process.env.NEXT_PUBLIC_API_URL, options);
}

export async function downloadAdminCsv(path: `/api/admin/${string}`, filename: string) {
  const response = await adminRequest(path);
  if (!response.ok) throw new Error("No se pudo exportar el archivo.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename + ".csv";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
