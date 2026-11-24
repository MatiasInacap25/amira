import { AuditTable, type AuditPageData } from "@/components/admin/audit-table";
import { readFilters, writeFilters } from "@/lib/admin/query";
import { checkAdmin, serverAdminFetch } from "@/lib/admin/server";

const filterKeys = ["q", "admin", "action", "entity", "date_from", "date_to", "sort", "offset"];

export default async function AuditPage({ searchParams }: PageProps<"/admin/auditoria">) {
  const access = await checkAdmin();
  if (!access) return null;
  const params = await searchParams;
  const filters = readFilters({ get: (key) => { const value = params[key]; return typeof value === "string" ? value : null; } }, filterKeys);
  const response = await serverAdminFetch(`/api/admin/audit?${writeFilters(filters)}`, access.accessToken);
  const data = response.ok ? await response.json() as AuditPageData : null;
  return (
    <main className="space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Auditoría</h1>
        <p>Historial de acciones de administración.</p>
      </header>
      <AuditTable filters={filters} data={data} detail={typeof params.detail === "string" ? params.detail : undefined} />
    </main>
  );
}
