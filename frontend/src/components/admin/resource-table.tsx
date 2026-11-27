"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { adminRequest } from "@/lib/admin/client";
import { adminDate, adminMoney, adminRut } from "@/lib/admin/formatters";
import { writeFilters, type AdminFilters } from "@/lib/admin/query";
import type { AdminPageData, AdminResource, AdminRow, ResourceField } from "@/lib/admin/resources";
import { DataTable, type RowAction } from "./data-table";
import { ConfirmDialog, DetailDrawer, ReasonDialog } from "./dialogs";
import { Filters } from "./filters";
import { StatusBadge } from "./status-badge";

type Mutation = { action: string; label: string; reason?: boolean };
const extraLabels: Record<string, string> = {
  phone: "Teléfono", created_at: "Fecha de registro", assurance: "Aseguramiento de sesión",
  claims: "Reclamos", recent_services: "Últimos servicios", open_services: "Servicios abiertos", service_types: "Servicios ofrecidos",
  driver_list: "Conductores", vehicle_list: "Vehículos", rating_list: "Valoraciones recientes",
  service_counts: "Servicios por estado", refunded: "Total reembolsado", paid_out: "Desembolsos recibidos",
  bank_status: "Cuenta bancaria", verifications: "Historial de verificaciones", assignments: "Asignaciones", description: "Descripción",
  commune_code: "Código de comuna", accepted_at: "Aceptada", revoked_at: "Revocada", year: "Año",
};
const labels: Record<string, string> = {
  company: "Empresa", independent_driver: "Conductor independiente", independent: "Independiente", blocked: "Bloqueado", active: "Activo",
  suspended: "Suspendido", disabled: "Deshabilitado", missing: "Sin documento", accepted: "Aceptada", revoked: "Revocada", expired: "Expirada",
};

function valueOf(value: unknown, field?: ResourceField) {
  if (value == null || value === "") return "Sin dato";
  if (field?.format === "date") return adminDate(String(value));
  if (field?.format === "money") return adminMoney(Number(value));
  if (field?.format === "rut") return adminRut(String(value));
  if (field?.format === "status") return <StatusBadge status={String(value)} label={labels[String(value)]} />;
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (Array.isArray(value)) return value.length ? <ul className="list-disc space-y-1 pl-5">
    {value.map((entry, index) => <li key={index}>{typeof entry === "object" && entry !== null
      ? Object.entries(entry).map(([key, data]) => key.endsWith("_at") && data ? adminDate(String(data)) : labels[String(data)] ?? String(data ?? "—")).join(" · ")
      : String(entry)}</li>)}
  </ul> : "Sin registros";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function ResourceTable({ resource, data, filters, detail, detailId }: {
  resource: AdminResource; data: AdminPageData | null; filters: AdminFilters;
  detail: AdminRow | null; detailId?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [mutation, setMutation] = useState<{ row: AdminRow; choice: Mutation } | null>(null);
  const [saving, setSaving] = useState(false);
  const [edit, setEdit] = useState<AdminRow | null>(null);
  const title = (row: AdminRow) => String(row.name ?? row.email ?? row.plate ?? row.id);
  const showDetail = (id?: string) => {
    const query = writeFilters(id ? { ...filters, detail: id } : filters).toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };
  const actions = (row: AdminRow): RowAction[] => {
    const result: RowAction[] = [{ label: "Ver detalle", onClick: () => showDetail(row.id) }];
    const add = (action: string, label: string, reason = false) => result.push({ label, onClick: () => setMutation({ row, choice: { action, label, reason } }) });
    if (resource.edits) result.push({ label: pathname.endsWith("/clientes") ? "Editar datos de contacto" : "Editar", onClick: () => setEdit(row) });
    const id = encodeURIComponent(row.id);
    const link = (slug: string, key: string, label: string, value = id) => result.push({ label, href: `/admin/${slug}?${key}=${value}` });
    if (pathname.endsWith("/clientes")) {
      if (row.status === "blocked") add("unblock", "Desbloquear");
      else add("block", "Bloquear", true);
      link("servicios", "customer", "Ver servicios");
      link("pagos", "customer", "Ver pagos");
    } else if (pathname.endsWith("/proveedores")) {
      if (row.status === "suspended") add("reactivate", "Reactivar");
      else add("suspend", "Suspender", true);
      if (row.published) {
        add("unpublish", "Despublicar", true);
        if (row.status !== "suspended") result.push({ label: "Ver perfil público", href: `/prestadores/${id}`, newTab: true });
      } else if (row.status !== "suspended") add("publish", "Volver a publicar");
      link("conductores", "provider", "Ver conductores");
      link("vehiculos", "provider", "Ver vehículos");
      link("servicios", "provider", "Ver servicios");
      link("cuentas-bancarias", "provider", "Ver cuenta bancaria");
    } else if (pathname.endsWith("/conductores")) {
      if (row.status === "blocked") add("unblock", "Desbloquear");
      else add("block", "Bloquear", true);
      link("documentos", "driver", "Ver documento de verificación");
      link("servicios", "driver", "Ver servicios asignados");
    } else if (pathname.endsWith("/invitaciones") && row.status === "pending") add("revoke", "Revocar", true);
    else if (pathname.endsWith("/vehiculos")) {
      if (row.status === "disabled") add("enable", "Habilitar");
      else add("disable", "Deshabilitar", true);
    }
    return result;
  };
  const save = async (row: AdminRow, action: string, body: Record<string, unknown>) => {
    setSaving(true);
    try {
      const response = await adminRequest(`${resource.path}/${encodeURIComponent(row.id)}/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(typeof error?.detail === "string" ? error.detail : "No se pudo completar la acción.");
      }
      setMutation(null);
      setEdit(null);
      toast.success("Cambios guardados.");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No se pudo completar la acción.");
    } finally {
      setSaving(false);
    }
  };
  const Dialog = mutation?.choice.reason ? ReasonDialog : ConfirmDialog;
  return <>
    <Filters key={writeFilters(filters).toString()} fields={resource.filters} filters={filters} initial={resource.defaults}
      exportPath={`${resource.path}/export.csv`} filename={pathname.split("/").at(-1)} />
    <DataTable
      columns={resource.fields.map((field) => ({ title: field.label, sort: field.sort, cell: (row: AdminRow) =>
        field.key === "provider" && typeof row.provider_id === "string"
          ? <Link className="underline" href={`/admin/proveedores?detail=${encodeURIComponent(row.provider_id)}`}>{String(row.provider ?? "Sin dato")}</Link>
          : valueOf(row[field.key], field),
      }))}
      rows={data?.items ?? []} rowId={(row) => row.id} rowLabel={title} onDetail={(row) => showDetail(row.id)}
      actions={actions} filters={filters} pathname={pathname} total={data?.total ?? 0} limit={data?.limit ?? 20} offset={data?.offset ?? 0}
      error={!data} onRetry={() => router.refresh()}
    />
    {detailId && <DetailDrawer title={detail ? title(detail) : "Detalle no disponible"} onClose={() => showDetail()}>
      {detail ? <dl className="grid gap-2">
        {resource.fields.map((field) => <div key={field.key}><dt className="font-semibold">{field.label}</dt><dd className="break-words">{valueOf(detail[field.key], field)}</dd></div>)}
        {Object.entries(extraLabels).filter(([key]) => key in detail && !resource.fields.some((field) => field.key === key)).map(([key, label]) =>
          <div key={key}><dt className="font-semibold">{label}</dt><dd className="break-words">{valueOf(detail[key], key.endsWith("_at") ? { key, label, format: "date" } : ["refunded", "paid_out"].includes(key) ? { key, label, format: "money" } : undefined)}</dd></div>)}
      </dl> : <p>No se pudo cargar el registro.</p>}
    </DetailDrawer>}
    {mutation && <Dialog title={`${mutation.choice.label}: ${title(mutation.row)}`}
      consequence={mutation.choice.action === "suspend" ? `El perfil se ocultará. Sus ${Number(mutation.row.open_services ?? 0)} servicios abiertos no se cancelarán.` : "La acción quedará registrada en la auditoría."}
      pending={saving} onClose={() => { if (!saving) setMutation(null); }}
      onConfirm={(reason) => { void save(mutation.row, mutation.choice.action, reason ? { reason } : {}); }} />}
    {edit && resource.edits && <DetailDrawer title={`Editar: ${title(edit)}`} onClose={() => { if (!saving) setEdit(null); }}>
      <form className="grid gap-4" onSubmit={(event) => {
        event.preventDefault();
        const fields = Object.fromEntries([...new FormData(event.currentTarget)].map(([key, value]) => [key, String(value).trim() || null]));
        void save(edit, "edit", { fields });
      }}>
        {resource.edits.map(({ key, label, type, required }) =>
          <label className="grid gap-1" key={key}>{label}
            <input className="admin-input" name={key} type={type ?? "text"} required={required}
              step={key === "maximum_weight" ? ".01" : undefined} defaultValue={String(edit[key] ?? "")} />
          </label>)}
        <button className="admin-button admin-primary" type="submit" disabled={saving}>Guardar cambios</button>
      </form>
    </DetailDrawer>}
  </>;
}
