"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminRequest, downloadAdminFile } from "@/lib/admin/client";
import { adminDate, adminMoney, adminRut } from "@/lib/admin/formatters";
import { writeFilters, type AdminFilters } from "@/lib/admin/query";
import type { AdminPageData, AdminResource, AdminRow, ResourceField } from "@/lib/admin/resources";
import { DataTable, type RowAction } from "./data-table";
import { ConfirmDialog, DetailDrawer, ReasonDialog } from "./dialogs";
import { Filters } from "./filters";
import { StatusBadge } from "./status-badge";
import { PayoutRelease } from "./payout-release";
import { AdminTranscript } from "./transcript";

type Mutation = { action: string; label: string; reason?: boolean };
const extraLabels: Record<string, string> = {
  phone: "Teléfono", created_at: "Fecha de registro", assurance: "Aseguramiento de sesión",
  claims: "Reclamos", recent_services: "Últimos servicios", open_services: "Servicios abiertos", service_types: "Servicios ofrecidos",
  driver_list: "Conductores", vehicle_list: "Vehículos", rating_list: "Valoraciones recientes",
  service_counts: "Servicios por estado", refunded: "Total reembolsado", paid_out: "Desembolsos recibidos",
  review_reason: "Motivo de la revisión", resolution: "Resolución", resolution_reason: "Motivo de la resolución",
  resolved_at: "Resuelto el", service_status: "Estado del servicio", payment_status: "Estado del pago", payout_status: "Estado del desembolso",
  started_at: "Inicio del servicio", completed_at: "Término del servicio", cancelled_at: "Cancelación del servicio",
  origin_address: "Dirección de origen", destination_address: "Dirección de destino", cargo_measurements: "Medidas de carga",
  estimated_weight: "Peso estimado", estimated_volume: "Volumen estimado", linked_quotes: "Cotizaciones", is_exclusive: "Exclusividad",
  payment_confirmed_at: "Pago confirmado", net: "Neto", iva: "IVA del servicio", commission: "Comisión", carrier_amount: "Neto del transportista",
  linked_services: "Servicios vinculados", ordered_stops: "Paradas", assigned_crew: "Vehículo y conductor",
  transactions: "Transacciones del proveedor", refunds: "Reembolsos",
  confirmed_at: "Confirmado el", quotation_id: "Cotización", bank_status: "Cuenta bancaria", verifications: "Historial de verificaciones", assignments: "Asignaciones", description: "Descripción",
  commune_code: "Código de comuna", accepted_at: "Aceptada", revoked_at: "Revocada", year: "Año",
};
const labels: Record<string, string> = {
  company: "Empresa", independent_driver: "Conductor independiente", independent: "Independiente", blocked: "Bloqueado", active: "Activo",
  inactive: "Desactivado", region: "Región", commune: "Comuna", user: "Usuario", profile: "Perfil",
  simulated: "Simulado", mercado_pago: "Mercado Pago", customer: "Cliente", provider: "Proveedor", admin: "Admin",
  claim: "Reclamo", window: "Plazo de reclamo vigente", bank_account: "Sin cuenta aprobada", payment: "Sin pago aprobado", none: "Sin bloqueo",
  released: "Liberado", criminal_record: "Certificado de antecedentes", driver_record: "Hoja de vida", resolved: "Resuelto",
  suspended: "Suspendido", disabled: "Deshabilitado", missing: "Sin documento", accepted: "Aceptada", revoked: "Revocada", expired: "Expirada",
};

const automaticResults: Record<string, string> = {
  in_review: "Auténtico con anotaciones",
  verified: "Verificado automáticamente",
  rejected: "Rechazado automáticamente",
};

function valueOf(value: unknown, field?: ResourceField) {
  if (value == null || value === "") return "Sin dato";
  if (field?.format === "date") return adminDate(String(value));
  if (field?.format === "money") return adminMoney(Number(value));
  if (field?.format === "rut") return adminRut(String(value));
  if (field?.key === "result" && typeof value === "string") return automaticResults[value] ?? value;
  if (field?.format === "status") return <StatusBadge status={String(value)} label={labels[String(value)]} />;
  if (field?.key === "is_exclusive") return value ? "Exclusivo" : "Compartido";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (Array.isArray(value)) return value.length ? <ul className="list-disc space-y-1 pl-5">
    {value.map((entry, index) => <li key={index}>{typeof entry === "object" && entry !== null
      ? Object.entries(entry).map(([key, data]) => key.endsWith("_at") && data ? adminDate(String(data)) : labels[String(data)] ?? String(data ?? "—")).join(" · ")
      : String(entry)}</li>)}
  </ul> : "Sin registros";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function resourceCellHref(field: string, row: AdminRow) {
  if (field === "provider" && typeof row.provider_id === "string") return `/admin/proveedores?detail=${encodeURIComponent(row.provider_id)}`;
  if (field === "service_id" && typeof row.service_id === "string") return `/admin/servicios?detail=${encodeURIComponent(row.service_id)}`;
  if (field === "request_id" && typeof row.request_id === "string") return `/admin/solicitudes?detail=${encodeURIComponent(row.request_id)}`;
}

export function ResourceTable({ resource, data, filters, detail, detailId, live = false }: {
  resource: AdminResource; data: AdminPageData | null; filters: AdminFilters;
  detail: AdminRow | null; detailId?: string; live?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [mutation, setMutation] = useState<{ row: AdminRow; choice: Mutation } | null>(null);
  const [saving, setSaving] = useState(false);
  const [edit, setEdit] = useState<AdminRow | null>(null);
  const watching = live && detail?.status === "in_progress";
  useEffect(() => {
    if (!watching) return;
    const timer = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [router, watching]);
  const title = (row: AdminRow) => String(row.name ?? row.email ?? row.plate ?? row.driver ?? row.id);
  const showDetail = (id?: string) => {
    const query = writeFilters(id ? { ...filters, detail: id } : filters).toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };
  const actions = (row: AdminRow): RowAction[] => {
    const result: RowAction[] = [{ label: "Ver detalle", onClick: () => showDetail(row.id) }];
    const add = (action: string, label: string, reason = false, disabled?: string) =>
      result.push({ label, disabled, onClick: () => setMutation({ row, choice: { action, label, reason } }) });
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
    } else if (pathname.endsWith("/documentos")) {
      const blocked = row.status !== "in_review" ? "El documento no está en revisión." : undefined;
      add("approve", "Aprobar", false, blocked);
      add("reject", "Rechazar", true, blocked);
    } else if (pathname.endsWith("/cuentas-bancarias")) {
      add("approve", "Aprobar", false, !row.matches ? "El RUT del titular no coincide con el del proveedor" :
        row.status !== "pending" ? "La cuenta no está pendiente." : undefined);
      add("reject", "Rechazar", true, row.status !== "pending" ? "La cuenta no está pendiente." : undefined);
      add("disable", "Deshabilitar", true, row.status !== "active" ? "La cuenta no está activa." : undefined);
    } else if (pathname.endsWith("/reclamos")) {
      const blocked = row.status !== "open" ? "El reclamo no está abierto." : undefined;
      add("resolve_customer", "Resolver a favor del cliente", true, blocked);
      add("resolve_provider", "Resolver a favor del proveedor", true, blocked);
      if (typeof row.service_id === "string") link("chats", "service", "Ver chat del servicio", encodeURIComponent(row.service_id));
    } else if (pathname.endsWith("/valoraciones")) {
      if (row.visible) add("hide", "Ocultar", true);
      else add("show", "Mostrar");
    } else if (pathname.endsWith("/solicitudes")) {
      link("cotizaciones", "request", "Ver cotizaciones");
      link("chats", "request", "Ver chat");
    } else if (pathname.endsWith("/cotizaciones")) {
      if (typeof row.request_id === "string") link("solicitudes", "detail", "Ver solicitud", encodeURIComponent(row.request_id));
      if (row.status === "paid") link("pagos", "quotation", "Ver pago");
    } else if (pathname.endsWith("/servicios")) {
      if (row.status === "in_progress") result.push({ label: "Ver ubicación en vivo", href: `${pathname}?${writeFilters({ ...filters, detail: row.id, live: "1" })}` });
      add("cancel", "Cancelar", true, row.status !== "confirmed" ? "Solo se pueden cancelar servicios confirmados." : undefined);
      const destinations = [["payment_id", "pagos", "Ver pago"], ["payout_id", "desembolsos", "Ver desembolso"],
        ["chat_id", "chats", "Ver chat"], ["claim_id", "reclamos", "Ver reclamo"]] as const;
      for (const [key, slug, label] of destinations) {
        const value = row[key];
        if (typeof value === "string") link(slug, "detail", label, encodeURIComponent(value));
      }
    } else if (pathname.endsWith("/pagos")) {
      result.push({ label: "Ver transacciones del proveedor", onClick: () => showDetail(row.id) });
      if (typeof row.service_id === "string") link("servicios", "detail", "Ver servicio", encodeURIComponent(row.service_id));
      const why = row.status !== "approved" ? "Solo se puede reembolsar un pago aprobado" :
        row.already_paid_out || row.already_refunded ? "El servicio ya tiene un desembolso o reembolso." :
        row.payment_provider !== "simulated" ? "Solo se pueden reembolsar pagos simulados." :
        row.service_status !== "confirmed" ? "El flujo de cancelación requiere un servicio confirmado." : undefined;
      add("refund", "Reembolsar", true, why);
    } else if (pathname.endsWith("/reembolsos") || pathname.endsWith("/desembolsos")) {
      if (typeof row.service_id === "string") link("servicios", "detail", "Ver servicio", encodeURIComponent(row.service_id));
      if (typeof row.payment_id === "string") link("pagos", "detail", "Ver pago", encodeURIComponent(row.payment_id));
      if (resource.path.endsWith("/payouts")) result.push({ label: "Descargar comprobante", onClick: () => {
        void downloadAdminFile(`${resource.path}/${id}/receipt`, `desembolso-${id}.html`)
          .catch(() => toast.error("No se pudo descargar el comprobante."));
      } });
    } else if (resource.path === "/api/admin/catalog/service-types") {
      add("deactivate", "Desactivar", false, row.status === "inactive" ? "El tipo ya está desactivado." : undefined);
      add("delete", "Eliminar", false, row.referenced ? "Este tipo está referenciado. Puedes desactivarlo." : undefined);
    } else if (pathname.endsWith("/rutas-compartidas")) {
      add("unpublish", "Despublicar", true, !row.published ? "El viaje no está publicado." : undefined);
      add("close", "Cerrar a nuevas solicitudes", false, !row.accepts_requests ? "El viaje ya está cerrado." : undefined);
      if (row.published && row.accepts_requests) result.push({ label: "Ver en el sitio público", href: `/rutas-compartidas#route-${id}`, newTab: true });
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
      if (pathname.endsWith("/documentos") && detailId === row.id) {
        const remaining = data?.items.filter((candidate) => candidate.id !== row.id && candidate.status === "in_review") ?? [];
        showDetail(remaining[0]?.id);
      }
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No se pudo completar la acción.");
    } finally {
      setSaving(false);
    }
  };
  const Dialog = mutation?.choice.reason ? ReasonDialog : ConfirmDialog;
  return <>
    {resource.path.endsWith("/payout-candidates") && <PayoutRelease />}
    <Filters key={writeFilters(filters).toString()} fields={resource.filters} filters={filters} initial={resource.defaults}
      exportPath={`${resource.path}/export.csv`} filename={pathname.split("/").at(-1)} />
    <DataTable
      columns={resource.fields.map((field) => ({
        title: field.label,
        sort: field.sort,
        format: field.format === "money" || field.format === "date" ? field.format : undefined,
        identifier: (row: AdminRow) => field.key === "id" || field.key.endsWith("_id") ? row[field.key] : undefined,
        href: (row: AdminRow) => resourceCellHref(field.key, row),
        cell: (row: AdminRow, shortId?: string) => shortId ??
          (field.key === "provider" && typeof row.provider_id === "string" ? String(row.provider ?? "Sin dato")
            : field.key === "comment" && typeof row.comment === "string"
              ? <span className="block max-w-64 truncate" title={row.comment}>{row.comment}</span>
              : valueOf(row[field.key], field)),
      }))}
      rows={data?.items ?? []} rowId={(row) => row.id} rowLabel={title} onDetail={(row) => showDetail(row.id)}
      actions={actions} filters={filters} pathname={pathname} total={data?.total ?? 0} limit={data?.limit ?? 20} offset={data?.offset ?? 0}
      error={!data} onRetry={() => router.refresh()}
    />
    {detailId && <DetailDrawer wide={pathname.endsWith("/documentos")} title={detail ? title(detail) : "Detalle no disponible"} onClose={() => showDetail()}>
      {detail ? <>
        {(pathname.endsWith("/chats") || (pathname.endsWith("/reclamos") && typeof detail.chat_id === "string")) &&
          <AdminTranscript key={detail.id} chatId={pathname.endsWith("/chats") ? detail.id : String(detail.chat_id)}
            hasClaim={pathname.endsWith("/reclamos") || detail.has_claim === true} />}
        {Array.isArray(detail.images) && detail.images.length > 0 && <section className="admin-card"><h3 className="font-semibold">Imágenes de la solicitud</h3>
          {detail.images.filter((image): image is string => typeof image === "string").map((image, index) =>
            <a className="underline" key={image} href={image} target="_blank" rel="noopener noreferrer">Ver imagen {index + 1}</a>)}
        </section>}
        {pathname.endsWith("/servicios") && (watching || detail.last_location != null) &&
          <section className="admin-card" aria-label="Última ubicación"><h3 className="font-semibold">{watching ? "Ubicación en vivo" : "Última ubicación"}</h3>
            <p>{detail.last_location ? valueOf(detail.last_location) : "Sin ubicación disponible."}</p>
          </section>}
        {pathname.endsWith("/documentos") && <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <section>
            <h3 className="mb-2 font-semibold">Certificado PDF</h3>
            {typeof detail.pdf_url === "string" ? <iframe src={detail.pdf_url} title="Certificado PDF" className="h-80 w-full rounded border" referrerPolicy="no-referrer" /> : <p>Sin PDF disponible.</p>}
          </section>
          <section>
            <h3 className="mb-2 font-semibold">Resultado automático{typeof detail.provider === "string" ? ` · ${detail.provider}` : ""}</h3>
            <p>{valueOf(detail.result, { key: "result", label: "Resultado automático" })}</p>
            <h3 className="my-2 font-semibold">Anotaciones</h3>
            <div className="break-words">{valueOf(detail.annotations)}</div>
          </section>
        </div>}
        {pathname.endsWith("/documentos") && detail.status === "in_review" && <div className="mb-4 flex gap-2">
          <button className="admin-button admin-primary" type="button" onClick={() => setMutation({ row: detail, choice: { action: "approve", label: "Aprobar" } })}>Aprobar</button>
          <button className="admin-button" type="button" onClick={() => setMutation({ row: detail, choice: { action: "reject", label: "Rechazar", reason: true } })}>Rechazar</button>
        </div>}
        {[["evidence_url", "Ver evidencia del cliente"], ["delivery_url", "Ver foto de entrega"]].map(([key, label]) =>
          typeof detail[key] === "string" ? <p key={key}><a className="underline" target="_blank" rel="noopener noreferrer" href={detail[key]}>{label}</a></p> : null)}
        <dl className="grid gap-2">
        {resource.fields.map((field) => <div key={field.key}><dt className="font-semibold">{field.label}</dt><dd className="break-words">{valueOf(detail[field.key], field)}</dd></div>)}
        {Object.entries(extraLabels).filter(([key]) => key in detail && !resource.fields.some((field) => field.key === key)).map(([key, label]) =>
          <div key={key}><dt className="font-semibold">{label}</dt><dd className="break-words">{valueOf(detail[key], key.endsWith("_at") ? { key, label, format: "date" } : ["refunded", "paid_out", "net", "iva", "commission", "carrier_amount"].includes(key) ? { key, label, format: "money" } : undefined)}</dd></div>)}
        </dl></> : <p>No se pudo cargar el registro.</p>}
    </DetailDrawer>}
    {mutation && <Dialog title={`${mutation.choice.label}: ${title(mutation.row)}`}
      consequence={mutation.choice.action === "suspend" ? `El perfil se ocultará. Sus ${Number(mutation.row.open_services ?? 0)} servicios abiertos no se cancelarán.` : mutation.choice.action === "delete" ? "El tipo de servicio se eliminará de forma permanente."
        : mutation.choice.action === "deactivate" ? "El tipo se ocultará en el catálogo público sin alterar sus referencias."
        : ["cancel", "refund"].includes(mutation.choice.action) ? "El servicio se cancelará y el cliente recibirá un reembolso simulado del 100 %, sin retención." : mutation.choice.action === "resolve_customer"
        ? "El servicio se cancelará y el pago simulado se reembolsará por completo."
        : mutation.choice.action === "resolve_provider" ? "El servicio volverá a completado y aplicarán las reglas normales de desembolso."
        : "La acción quedará registrada en la auditoría."}
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
