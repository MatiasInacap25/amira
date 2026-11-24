import Link from "next/link";
import { checkAdmin } from "@/lib/admin/server";

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
  return (
    <>
      <header className="flex gap-4 p-6">
        <Link href="/admin">Amira Admin</Link>
        <Link href="/admin/auditoria">Auditoría</Link>
        <span>{access.admin.email}</span>
      </header>
      {children}
    </>
  );
}
