import Link from "next/link";
import { checkAdmin, serverAdminFetch } from "@/lib/admin/server";

type AuditEntry = {
  id: string;
  admin_user_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  created_at: string;
};

type AuditPageData = { items: AuditEntry[]; total: number; limit: number; offset: number };

const dateTime = new Intl.DateTimeFormat("es-CL", {
  dateStyle: "short", timeStyle: "short", timeZone: "America/Santiago",
});
const entityPaths: ReadonlyMap<string, string> = new Map([
  ["customer", "clientes"], ["provider", "proveedores"], ["driver", "conductores"],
  ["invitation", "invitaciones"], ["verification", "documentos"], ["bank_account", "cuentas-bancarias"],
  ["claim", "reclamos"], ["rating", "valoraciones"], ["request", "solicitudes"], ["quotation", "cotizaciones"],
  ["service", "servicios"], ["trip", "rutas-compartidas"], ["vehicle", "vehiculos"], ["chat", "chats"],
  ["payment", "pagos"], ["refund", "reembolsos"], ["payout", "desembolsos"], ["service_type", "catalogos"],
]);

const filterFields = [
  ["q", "Buscar", "search"], ["admin", "Admin", "text"], ["action", "Acción", "text"],
  ["entity", "Entidad", "text"], ["date_from", "Desde", "date"], ["date_to", "Hasta", "date"],
] as const;

export default async function AuditPage({ searchParams }: PageProps<"/admin/auditoria">) {
  const access = await checkAdmin();
  if (!access) return null;
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const key of [...filterFields.map(([name]) => name), "sort", "offset"]) {
    const value = params[key];
    if (typeof value === "string" && value.trim()) query.set(key, value.trim());
  }
  const response = await serverAdminFetch(`/api/admin/audit?${query}`, access.accessToken);
  const data = response.ok ? await response.json() as AuditPageData : null;
  function pageHref(offset: number) {
    const next = new URLSearchParams(query);
    next.set("offset", String(offset));
    return `/admin/auditoria?${next}`;
  }
  const sort = new URLSearchParams(query);
  sort.delete("offset");
  sort.set("sort", query.get("sort") === "created_at" ? "-created_at" : "created_at");
  return (
    <main className="space-y-4 p-6">
      <header>
        <h1>Auditoría</h1>
        <p>Historial de acciones de administración.</p>
      </header>
      <form action="/admin/auditoria" className="flex flex-wrap items-end gap-3">
        {filterFields.map(([key, title, type]) => (
          <label key={key}>{title}<input className="ml-2 rounded border px-2 py-1" name={key} type={type} defaultValue={query.get(key) ?? ""} /></label>
        ))}
        <button type="submit">Aplicar filtros</button>
        <Link href="/admin/auditoria">Limpiar filtros</Link>
      </form>
      {!data ? (
        <p role="alert">No se pudo cargar la auditoría. <Link href={`/admin/auditoria?${query}`}>Reintentar</Link></p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead><tr>
                <th scope="col"><Link href={`/admin/auditoria?${sort}`}>Fecha</Link></th>
                {["Admin", "Acción", "Entidad", "Motivo"].map((title) => <th key={title} scope="col">{title}</th>)}
              </tr></thead>
              <tbody>{data.items.map((entry) => {
                const path = entityPaths.get(entry.entity_type);
                const label = `${entry.entity_type}: ${entry.entity_id}`;
                return (
                  <tr key={entry.id}>
                    <td>{dateTime.format(new Date(entry.created_at))}</td>
                    <td>{entry.admin_user_id}</td>
                    <td>{entry.action}</td>
                    <td>{path ? <Link href={`/admin/${path}?detail=${encodeURIComponent(entry.entity_id)}`}>{label}</Link> : label}</td>
                    <td>{entry.reason ?? "—"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          {data.items.length ? (
            <nav aria-label="Paginación de auditoría" className="flex gap-4">
              <span>Mostrando {data.offset + 1}–{data.offset + data.items.length} de {data.total}</span>
              {data.offset > 0 && <Link href={pageHref(Math.max(0, data.offset - data.limit))}>Anterior</Link>}
              {data.offset + data.limit < data.total && <Link href={pageHref(data.offset + data.limit)}>Siguiente</Link>}
            </nav>
          ) : <p>No hay resultados con estos filtros</p>}
        </>
      )}
    </main>
  );
}
