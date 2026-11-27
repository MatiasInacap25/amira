import type { FilterField } from "@/components/admin/filters";

export type AdminRow = { id: string; [key: string]: unknown };
export type AdminPageData = { items: AdminRow[]; total: number; limit: number; offset: number };
export type ResourceField = { key: string; label: string; format?: "date" | "money" | "rut" | "status" | "yesno"; sort?: string };
export type AdminResource = {
  title: string;
  description: string;
  path: `/api/admin/${string}`;
  fields: ResourceField[];
  filters: FilterField[];
  edits?: { key: string; label: string; type?: string; required?: boolean }[];
  defaults?: Record<string, string>;
};

const field = (key: string, label: string, format?: ResourceField["format"], sort?: string) => ({ key, label, format, sort });
const status = field("status", "Estado", "status");
const created = field("created_at", "Creado", "date", "created_at");
const options = (key: string, label: string, values: [string, string][]): FilterField => ({
  key, label, options: values.map(([value, label]) => ({ value, label })),
});
const state = (other: string, label: string) => options("status", "Estado", [["active", "Activo"], [other, label]]);
const providerFilter = { key: "provider", label: "Proveedor" };
const dates = [{ key: "start", label: "Desde", type: "date" }, { key: "end", label: "Hasta", type: "date" }] as const;

export const adminResources: Record<string, AdminResource> = {
  clientes: {
    title: "Clientes", description: "Consulta clientes y administra el acceso a sus cuentas.", path: "/api/admin/people/customers",
    fields: [field("name", "Nombre completo"), field("national_id", "RUT", "rut"), field("email", "Correo"),
      field("phone", "Teléfono"), field("created_at", "Fecha de registro", "date", "created_at"),
      field("services", "N° servicios"), field("paid", "Total pagado", "money", "paid"), status],
    filters: [state("blocked", "Bloqueado"), ...dates, options("has_claim", "Con reclamos", [["true", "Sí"], ["false", "No"]])],
    edits: [{ key: "first_name", label: "Nombre", required: true }, { key: "last_name", label: "Apellido", required: true }, { key: "phone", label: "Teléfono", type: "tel" }],
  },
  proveedores: {
    title: "Proveedores", description: "Gestiona la publicación y el estado de los perfiles de transporte.", path: "/api/admin/people/providers",
    fields: [field("name", "Nombre / razón social"), field("kind", "Tipo", "status"), field("company_tax_id", "RUT empresa", "rut"),
      field("owner", "Dueño"), field("owner_email", "Correo del dueño"), field("published", "Publicado", "yesno"),
      field("drivers", "Conductores"), field("vehicles", "Vehículos"), field("services", "Servicios completados"), field("rating", "Calificación promedio"), status],
    filters: [options("kind", "Tipo", [["company", "Empresa"], ["independent_driver", "Conductor independiente"]]),
      options("published", "Publicado", [["true", "Sí"], ["false", "No"]]), state("suspended", "Suspendido"), { key: "region", label: "Código de región" }],
    edits: [{ key: "name", label: "Nombre", required: true }, { key: "description", label: "Descripción" }, { key: "commune_code", label: "Código de comuna" }],
  },
  conductores: {
    title: "Conductores", description: "Consulta conductores, sus verificaciones y sus asignaciones.", path: "/api/admin/people/drivers",
    fields: [field("name", "Nombre"), field("national_id", "RUT", "rut"), field("email", "Correo"), field("kind", "Tipo", "status"),
      field("provider", "Perfil / empresa"), field("verification", "Verificación", "status"), field("services", "Servicios asignados"), field("last_service", "Último servicio", "date"), status],
    filters: [options("kind", "Tipo", [["company", "De empresa"], ["independent", "Independiente"]]), providerFilter,
      options("verification", "Verificación", [["verified", "Verificado"], ["in_review", "En revisión"], ["rejected", "Rechazado"], ["missing", "Sin documento"]])],
  },
  invitaciones: {
    title: "Invitaciones", description: "Consulta y revoca invitaciones pendientes de conductores.", path: "/api/admin/people/invitations",
    fields: [field("email", "Correo invitado"), field("provider", "Empresa"), field("created_at", "Enviada", "date", "created_at"),
      field("expires_at", "Expira", "date"), status, field("attempts", "Intentos")],
    filters: [options("status", "Estado", [["pending", "Pendiente"], ["accepted", "Aceptada"], ["expired", "Expirada"], ["revoked", "Revocada"]]), providerFilter],
  },
  vehiculos: {
    title: "Vehículos", description: "Consulta y administra los vehículos de los proveedores.", path: "/api/admin/people/vehicles",
    fields: [field("plate", "Patente"), field("provider", "Proveedor"), field("brand", "Marca"), field("model", "Modelo"),
      field("maximum_weight", "Peso máximo (kg)"), field("services", "Servicios realizados"), created, status],
    filters: [providerFilter, state("disabled", "Deshabilitado")],
    edits: [{ key: "brand", label: "Marca", required: true }, { key: "model", label: "Modelo", required: true },
      { key: "year", label: "Año", type: "number" }, { key: "maximum_weight", label: "Peso máximo (kg)", type: "number" }],
  },
  documentos: {
    title: "Documentos de conductores", description: "Revisa el resultado automático y decide sobre los certificados pendientes.",
    path: "/api/admin/review/documents", defaults: { status: "in_review" },
    fields: [field("driver", "Conductor"), field("national_id", "RUT", "rut"), field("provider", "Empresa"), field("document_type", "Documento", "status"),
      field("created_at", "Subido", "date", "created_at"), field("result", "Resultado automático"), status,
      field("reviewer", "Revisado por"), field("reviewed_at", "Revisado el", "date")],
    filters: [options("status", "Estado", [["in_review", "En revisión"], ["verified", "Verificado"], ["rejected", "Rechazado"]]),
      { key: "driver", label: "ID del conductor" }, ...dates],
  },
  "cuentas-bancarias": {
    title: "Cuentas bancarias", description: "Comprueba la titularidad antes de habilitar desembolsos.",
    path: "/api/admin/review/bank-accounts",
    fields: [field("provider", "Proveedor"), field("bank_name", "Banco"), field("account_type", "Tipo de cuenta"),
      field("masked_number", "Número"), field("holder_rut", "RUT titular", "rut"), field("profile_rut", "RUT del perfil", "rut"),
      field("matches", "Coincide", "yesno"), status, field("created_at", "Creada", "date", "created_at")],
    filters: [options("status", "Estado", [["pending", "Pendiente"], ["active", "Aprobada"], ["rejected", "Rechazada"], ["disabled", "Deshabilitada"]]),
      options("matches", "Coincide", [["true", "Sí"], ["false", "No"]]), providerFilter],
  },
  reclamos: {
    title: "Reclamos", description: "Revisa la evidencia y resuelve servicios en disputa.", path: "/api/admin/review/claims", defaults: { status: "open" },
    fields: [field("id", "N° reclamo"), field("service_id", "Servicio"), field("customer", "Cliente"), field("provider", "Proveedor"),
      field("reason", "Motivo"), created, field("open_days", "Días abierto", undefined, "open_days"), field("amount", "Monto en juego", "money"), status],
    filters: [options("status", "Estado", [["open", "Abierto"], ["resolved", "Resuelto"]]), providerFilter, { key: "service", label: "ID del servicio" }, ...dates],
  },
  valoraciones: {
    title: "Valoraciones", description: "Consulta y modera las valoraciones públicas.", path: "/api/admin/review/ratings",
    fields: [field("provider", "Proveedor"), field("customer", "Cliente"), field("service_id", "Servicio"),
      field("rating", "Nota"), field("comment", "Comentario"), field("created_at", "Fecha", "date", "created_at"), field("visible", "Visible", "yesno")],
    filters: [{ key: "rating", label: "Nota", type: "number" }, options("visible", "Visible", [["true", "Sí"], ["false", "No"]]), providerFilter],
  },
};
