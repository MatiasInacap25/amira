import "./admin.css";
import { Sidebar } from "@/components/admin/sidebar";
import Link from "next/link";
import { checkAdmin, serverAdminFetch } from "@/lib/admin/server";

function AdminAccessDenied() {
  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1>No tienes acceso al panel de administración.</h1>
      <Link href="/">Volver a Amira</Link>
    </main>
  );
}

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const access = await checkAdmin();
  if (!access) return <AdminAccessDenied />;
  const badges = await serverAdminFetch("/api/admin/badges", access.accessToken).catch(() => null);
  const counts = badges?.ok ? await badges.json() as Record<string, number> : {};

  return (
    <div className="admin-frame">
      <Sidebar email={access.admin.email} counts={counts} />
      <div className="admin-main">{children}</div>
    </div>
  );
}
