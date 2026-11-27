"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { DataTable } from "./data-table";
import { DetailDrawer } from "./dialogs";
import { Filters } from "./filters";
import { adminDate } from "@/lib/admin/formatters";
import { type AdminFilters, writeFilters } from "@/lib/admin/query";

export type AuditEntry = {
  id: string;
  admin_user_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};
export type AuditPageData = { items: AuditEntry[]; total: number; limit: number; offset: number };

const entityPaths: ReadonlyMap<string, string> = new Map([
  ["customer", "clientes"], ["provider", "proveedores"], ["driver", "conductores"],
  ["invitation", "invitaciones"], ["verification", "documentos"], ["bank_account", "cuentas-bancarias"],
  ["claim", "reclamos"], ["rating", "valoraciones"], ["request", "solicitudes"], ["quotation", "cotizaciones"],
  ["service", "servicios"], ["trip", "rutas-compartidas"], ["vehicle", "vehiculos"], ["chat", "chats"],
  ["payment", "pagos"], ["refund", "reembolsos"], ["payout", "desembolsos"], ["service_type", "catalogos"],
]);

const fields = [
  { key: "admin", label: "Admin" }, { key: "action", label: "Acción" }, { key: "entity", label: "Entidad" },
  { key: "date_from", label: "Desde", type: "date" }, { key: "date_to", label: "Hasta", type: "date" },
] as const;

function entityHref(row: AuditEntry) {
  const section = entityPaths.get(row.entity_type);
  return section ? `/admin/${section}?detail=${encodeURIComponent(row.entity_id)}` : undefined;
}

function entityLink(row: AuditEntry) {
  const href = entityHref(row);
  const name = `${row.entity_type}: ${row.entity_id}`;
  return href ? <Link href={href}>{name}</Link> : name;
}

export function AuditTable({ filters, data, detail }: { filters: AdminFilters; data: AuditPageData | null; detail: string | undefined }) {
  const router = useRouter();
  const pathname = usePathname();
  const entry = data?.items.find(({ id }) => id === detail);
  const open = (row: AuditEntry) => router.replace(`${pathname}?${writeFilters({ ...filters, detail: row.id })}`, { scroll: false });
  const close = () => router.replace(`${pathname}?${writeFilters(filters)}`, { scroll: false });
  return (
    <>
      <Filters key={writeFilters(filters).toString()} fields={fields} filters={filters}
        exportPath="/api/admin/audit/export.csv" filename="auditoria" />
      <DataTable
        columns={[
          { title: "Fecha", sort: "created_at", format: "date", cell: (row: AuditEntry) => adminDate(row.created_at) },
          { title: "Admin", identifier: (row) => row.admin_user_id, cell: (row, shortId) => shortId ?? row.admin_user_id },
          { title: "Acción", cell: (row) => row.action },
          { title: "Entidad", href: entityHref, identifier: (row) => row.entity_id, cell: (row, shortId) => `${row.entity_type}: ${shortId ?? row.entity_id}` },
          { title: "Motivo", cell: (row) => row.reason ?? "—" },
        ]}
        rows={data?.items ?? []} rowId={(row) => row.id} rowLabel={(row) => row.action} onDetail={open}
        actions={(row) => [{ label: "Ver detalle", onClick: () => open(row) }]}
        filters={filters} pathname={pathname} total={data?.total ?? 0} limit={data?.limit ?? 20} offset={data?.offset ?? 0}
        error={!data} onRetry={() => router.refresh()}
      />
      {entry && <DetailDrawer title="Detalle de auditoría" onClose={close}>
        <dl className="grid gap-2">
          <dt>Fecha</dt><dd>{adminDate(entry.created_at)}</dd>
          <dt>Admin</dt><dd>{entry.admin_user_id}</dd>
          <dt>Acción</dt><dd>{entry.action}</dd>
          <dt>Entidad</dt><dd>{entityLink(entry)}</dd>
          <dt>Motivo</dt><dd>{entry.reason ?? "—"}</dd>
        </dl>
        {[["Antes", entry.before], ["Después", entry.after]].map(([label, value]) => value
          ? <section key={String(label)} className="mt-4"><h3>{String(label)}</h3><pre className="whitespace-pre-wrap break-all">{JSON.stringify(value, null, 2)}</pre></section>
          : null)}
      </DetailDrawer>}
    </>
  );
}
