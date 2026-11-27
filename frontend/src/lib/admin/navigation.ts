import {
  Banknote, Building2, CarFront, ClipboardList, FileCheck, FileText, House, Landmark, ListTree,
  MailPlus, MessageSquare, Route, ScrollText, Settings, ShieldAlert, Star, Truck,
  UserRound, Wallet, WalletCards, Undo2,
} from "lucide-react";

export const adminNavigation = [
  { name: "General", links: [{ slug: "", label: "Principal", icon: House }] },
  { name: "Personas", links: [
    { slug: "clientes", label: "Clientes", icon: UserRound },
    { slug: "proveedores", label: "Proveedores", icon: Building2 },
    { slug: "conductores", label: "Conductores", icon: Truck },
    { slug: "invitaciones", label: "Invitaciones", icon: MailPlus },
  ] },
  { name: "Revisión", links: [
    { slug: "documentos", label: "Documentos de conductores", icon: FileCheck },
    { slug: "cuentas-bancarias", label: "Cuentas bancarias", icon: Landmark },
    { slug: "reclamos", label: "Reclamos", icon: ShieldAlert },
    { slug: "valoraciones", label: "Valoraciones", icon: Star },
  ] },
  { name: "Operación", links: [
    { slug: "solicitudes", label: "Solicitudes", icon: ClipboardList },
    { slug: "cotizaciones", label: "Cotizaciones", icon: FileText },
    { slug: "servicios", label: "Servicios", icon: Truck },
    { slug: "rutas-compartidas", label: "Rutas compartidas", icon: Route },
    { slug: "vehiculos", label: "Vehículos", icon: CarFront },
    { slug: "chats", label: "Chats", icon: MessageSquare },
  ] },
  { name: "Finanzas", links: [
    { slug: "pagos", label: "Pagos", icon: WalletCards },
    { slug: "reembolsos", label: "Reembolsos y cancelaciones", icon: Undo2 },
    { slug: "desembolsos", label: "Desembolsos", icon: Wallet },
    { slug: "finanzas", label: "Comisiones e IVA", icon: Banknote },
  ] },
  { name: "Sistema", links: [
    { slug: "catalogos", label: "Catálogos", icon: ListTree },
    { slug: "auditoria", label: "Auditoría", icon: ScrollText },
    { slug: "configuracion", label: "Configuración", icon: Settings },
  ] },
] as const;

export function adminHref(slug: string) {
  return slug ? `/admin/${slug}` : "/admin";
}
