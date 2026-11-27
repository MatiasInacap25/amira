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
  solicitudes: {
    title: "Solicitudes", description: "Consulta las solicitudes de transporte y su actividad.", path: "/api/admin/operations/requests",
    fields: [field("id", "N°"), field("customer", "Cliente"), field("provider", "Proveedor"), field("service_type", "Tipo de servicio"),
      field("origin", "Origen"), field("destination", "Destino"), field("requested_at", "Fecha solicitada", "date"), status,
      field("quotes", "N° cotizaciones"), created],
    filters: [options("status", "Estado", [["pending", "Pendiente"], ["accepted", "Aceptada"], ["rejected", "Rechazada"]]),
      { key: "service_type", label: "ID del tipo de servicio" }, { key: "region", label: "Código de región" }, providerFilter, ...dates],
  },
  cotizaciones: {
    title: "Cotizaciones", description: "Consulta cotizaciones y su desglose con IVA incluido.", path: "/api/admin/operations/quotations",
    fields: [field("id", "N°"), field("request_id", "Solicitud"), field("provider", "Proveedor"), field("customer", "Cliente"),
      field("amount", "Monto total", "money", "amount"), field("net", "Neto", "money"), field("iva", "IVA", "money"),
      field("commission", "Comisión estimada", "money"), status, field("expires_at", "Válida hasta", "date"), created],
    filters: [options("status", "Estado", [["pending", "Pendiente"], ["paid", "Pagada"], ["rejected", "Rechazada"], ["expired", "Expirada"], ["superseded", "Reemplazada"]]),
      providerFilter, { key: "request", label: "ID de la solicitud" }, { key: "minimum_amount", label: "Monto mínimo", type: "number" },
      { key: "maximum_amount", label: "Monto máximo", type: "number" }, ...dates],
  },
  servicios: {
    title: "Servicios", description: "Consulta servicios, asignaciones y movimientos operativos.", path: "/api/admin/operations/services",
    fields: [field("id", "N°"), field("customer", "Cliente"), field("provider", "Proveedor"), field("drivers", "Conductores"),
      field("vehicles", "Vehículos"), field("origin", "Origen"), field("destination", "Destino"), field("starts_at", "Inicio", "date"),
      field("completed_at", "Fin", "date"), field("amount", "Monto", "money"), status, field("payment_status", "Pago", "status"),
      field("payout_status", "Desembolso", "status"), field("is_exclusive", "Exclusividad")],
    filters: [options("status", "Estado", [["confirmed", "Confirmado"], ["in_progress", "En curso"], ["completed", "Completado"],
      ["disputed", "En reclamo"], ["cancelled", "Cancelado"]]), providerFilter, { key: "customer", label: "ID del cliente" },
      { key: "driver", label: "ID del conductor" }, options("exclusive", "Exclusivo", [["true", "Sí"], ["false", "No"]]),
      options("has_claim", "Con reclamo", [["true", "Sí"], ["false", "No"]]),
      options("payout_due", "Listo para desembolso", [["true", "Sí"], ["false", "No"]]), ...dates],
  },
  chats: {
    title: "Chats", description: "Consulta metadatos y solicita acceso auditado a las conversaciones.", path: "/api/admin/operations/chats",
    fields: [field("participants", "Participantes"), field("service_id", "Servicio"), field("last_message_at", "Último mensaje", "date"),
      field("messages", "N° mensajes"), created],
    filters: [{ key: "service", label: "ID del servicio" }, { key: "request", label: "ID de la solicitud" }],
  },
  "rutas-compartidas": {
    title: "Rutas compartidas", description: "Consulta viajes compartidos, paradas y servicios vinculados.", path: "/api/admin/operations/trips",
    fields: [field("id", "N°"), field("provider", "Proveedor"), field("origin", "Origen"), field("destination", "Destino"),
      field("departure_at", "Salida", "date", "departure_at"), status, field("published", "Publicado", "yesno"),
      field("accepts_requests", "Acepta solicitudes", "yesno"), field("services", "Servicios unidos"), field("stops", "Paradas")],
    filters: [{ key: "status", label: "Estado" }, options("published", "Publicado", [["true", "Sí"], ["false", "No"]]),
      options("accepts_requests", "Acepta solicitudes", [["true", "Sí"], ["false", "No"]]), ...dates],
  },
  pagos: {
    title: "Pagos", description: "Consulta pagos, evidencia verificada y reembolsos simulados.", path: "/api/admin/transactions/payments",
    fields: [field("id", "N°"), field("service_id", "Servicio"), field("quotation_id", "Cotización"), field("customer", "Cliente"),
      field("provider", "Proveedor"), field("amount", "Monto", "money", "amount"), field("net", "Neto", "money"), field("iva", "IVA", "money"),
      status, field("payment_provider", "Proveedor de pago", "status"), field("external_id", "ID externo"), created,
      field("confirmed_at", "Aprobado", "date")],
    filters: [options("status", "Estado", [["pending", "Pendiente"], ["approved", "Aprobado"], ["rejected", "Rechazado"]]),
      options("payment_provider", "Proveedor de pago", [["simulated", "Simulado"], ["mercado_pago", "Mercado Pago"]]),
      { key: "quotation", label: "ID de cotización" }, { key: "customer", label: "ID del cliente" }, { key: "service", label: "ID del servicio" },
      { key: "minimum_amount", label: "Monto mínimo", type: "number" }, { key: "maximum_amount", label: "Monto máximo", type: "number" }, ...dates],
  },
  reembolsos: {
    title: "Reembolsos y cancelaciones", description: "Consulta devoluciones y retenciones registradas.", path: "/api/admin/transactions/refunds",
    fields: [field("id", "N°"), field("payment_id", "Pago"), field("service_id", "Servicio"), field("customer", "Cliente"),
      field("amount", "Monto devuelto", "money"), field("retained", "Monto retenido", "money"), field("reason", "Motivo"),
      field("actor", "Iniciado por", "status"), field("created_at", "Fecha", "date", "created_at"), status],
    filters: [options("actor", "Iniciado por", [["customer", "Cliente"], ["provider", "Proveedor"], ["admin", "Admin"]]),
      { key: "service", label: "ID del servicio" }, ...dates],
  },
  desembolsos: {
    title: "Desembolsos", description: "Consulta desembolsos pendientes y sus bloqueos.", path: "/api/admin/transactions/payout-candidates",
    fields: [field("service_id", "Servicio"), field("provider", "Proveedor"), field("account_status", "Cuenta bancaria", "status"),
      field("amount", "Bruto", "money"), field("commission", "Comisión", "money"), field("net_amount", "Neto a pagar", "money"),
      field("completed_at", "Completado el", "date"), field("blocked_by", "Bloqueado por", "status")],
    filters: [providerFilter, ...dates],
  },
};

export const paidPayoutResource: AdminResource = {
  title: "Desembolsos", description: "Consulta desembolsos liberados y sus comprobantes.", path: "/api/admin/transactions/payouts",
  fields: [field("id", "N°"), field("service_id", "Servicio"), field("provider", "Proveedor"), field("amount", "Bruto", "money"),
    field("commission", "Comisión", "money"), field("net_amount", "Neto", "money"),
    field("external_id", "ID de proveedor"), field("confirmed_at", "Liberado el", "date"), status],
  filters: [providerFilter, ...dates], defaults: { tab: "paid" },
};

export const catalogResources: Record<string, AdminResource> = {
  "service-types": {
    title: "Catálogos", description: "Gestiona los tipos de servicio disponibles.", path: "/api/admin/catalog/service-types",
    fields: [field("name", "Nombre"), field("slug", "Identificador"), field("description", "Descripción"), status],
    filters: [options("status", "Estado", [["active", "Activo"], ["inactive", "Desactivado"]])],
    edits: [{ key: "name", label: "Nombre", required: true }, { key: "description", label: "Descripción" }],
  },
  "driver-types": {
    title: "Catálogos", description: "Consulta los tipos fijos de conductor.", path: "/api/admin/catalog/driver-types",
    fields: [field("name", "Nombre"), field("id", "Identificador fijo")],
    filters: [], defaults: { tab: "driver-types" },
  },
  locations: {
    title: "Catálogos", description: "Consulta los códigos de regiones y comunas.", path: "/api/admin/catalog/locations",
    fields: [field("name", "Nombre"), field("code", "Código"), field("kind", "Tipo", "status"), field("region", "Región")],
    filters: [], defaults: { tab: "locations" },
  },
  roles: {
    title: "Catálogos", description: "Consulta los roles fijos de usuario y perfil.", path: "/api/admin/catalog/roles",
    fields: [field("name", "Nombre"), field("code", "Código"), field("kind", "Tipo", "status")],
    filters: [], defaults: { tab: "roles" },
  },
};
