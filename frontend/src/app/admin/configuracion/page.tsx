import { type AdminConfiguration } from "@/lib/admin/finance";
import { adminData, checkAdmin } from "@/lib/admin/server";

function adapter(value: string | null) {
  return value === "simulated" ? "Simulado" : value === "mercado_pago" ? "Mercado Pago sandbox" : "No configurado";
}

export default async function ConfigurationPage() {
  const access = await checkAdmin();
  if (!access) return null;
  const config = await adminData<AdminConfiguration>("/api/admin/configuration", access.accessToken);
  return <main className="space-y-5 p-6">
    <header><h1 className="text-2xl font-semibold">Configuración</h1><p>Parámetros operativos de solo lectura.</p></header>
    {config ? <>
      <dl className="admin-card">
        <dt>Comisión</dt><dd>{config.commission_percent} %</dd>
        <dt>Entorno (APP_ENV)</dt><dd>{config.app_env}</dd>
        <dt>Adaptador de pagos</dt><dd>{adapter(config.payment_adapter)}</dd>
        <dt>Adaptador de desembolsos</dt><dd>{adapter(config.payout_adapter)}</dd>
        <dt>Plazo de reclamo</dt><dd>{config.claim_window_hours} horas</dd>
      </dl>
      <section className="admin-card"><h2 className="font-semibold">Administradores</h2><ul>{config.admins.map((admin) =>
        <li key={admin.user_id}>{admin.email ?? (admin.user_id === access.admin.user_id ? access.admin.email : "Correo no disponible")} · {admin.user_id}</li>)}</ul></section>
    </> : <p role="alert">No se pudo cargar la configuración.</p>}
  </main>;
}
