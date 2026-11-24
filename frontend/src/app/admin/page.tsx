import Link from "next/link";
import { DashboardPeriod } from "@/components/admin/finance-controls";
import { KpiCard } from "@/components/admin/kpi-card";
import { StatusBadge } from "@/components/admin/status-badge";
import { dashboardPeriod, type FinanceDay, type FinanceMovement, type FinanceSummary } from "@/lib/admin/finance";
import { adminDate, adminMoney } from "@/lib/admin/formatters";
import { adminData, checkAdmin } from "@/lib/admin/server";

const movementLabel = { payment: "Pago", refund: "Reembolso", payout: "Desembolso" };
const pending = [
  ["documentos", "Documentos de conductores", "in_review"], ["reclamos", "Reclamos abiertos", "open"],
  ["cuentas-bancarias", "Cuentas bancarias pendientes", "pending"],
] as const;
const money = (value: number | string) => adminMoney(Number(value));

export default async function AdminPage({ searchParams }: PageProps<"/admin">) {
  const access = await checkAdmin();
  if (!access) return null;
  const period = dashboardPeriod(await searchParams);
  const query = new URLSearchParams({ from: period.from, to: period.to });
  const [summary, days, movements] = await Promise.all([
    adminData<FinanceSummary>(`/api/admin/finance/summary?${query}`, access.accessToken),
    adminData<FinanceDay[]>(`/api/admin/finance/timeseries?${query}&bucket=day`, access.accessToken),
    adminData<FinanceMovement[]>("/api/admin/finance/movements?limit=10", access.accessToken),
  ]);
  return <main className="space-y-6 p-6">
    <header><h1 className="text-2xl font-semibold">Principal</h1><p>Resumen de actividad y movimientos de Amira.</p></header>
    <DashboardPeriod key={`${period.preset}:${query}`} period={period} />
    {!summary ? <p role="alert">No se pudo cargar el resumen del período. <Link href="/admin">Reintentar</Link></p> :
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard title="Recaudado" value={money(summary.collected)} />
        <KpiCard title="Reembolsado" value={money(summary.refunded)} />
        <KpiCard title="Recaudado neto" value={money(summary.net_collected)} />
        <KpiCard title="Por pagar a transportistas" value={money(summary.payout_due)}
          description={`${summary.payout_due_count} servicios, ${summary.payout_blocked_count} bloqueados por reclamo`} />
        <KpiCard title="Pagado a transportistas" value={money(summary.payout_paid)} />
        <KpiCard title="Comisiones" value={money(summary.commission_gross)}
          description={`Neto ${money(summary.commission_net)} · IVA ${money(summary.commission_iva)}`} />
        <KpiCard title="IVA débito de Amira" value={money(summary.platform_iva)}
          description="IVA de comisiones y retenciones por cancelación." />
        <KpiCard title="Servicios en curso" value={summary.service_counts.in_progress} />
        <KpiCard title="Servicios completados" value={summary.service_counts.completed} />
        <KpiCard title="Servicios cancelados" value={summary.service_counts.cancelled} />
        {pending.map(([key, label, status]) =>
          <KpiCard key={key} title={label} value={summary.pending[key] ?? 0} href={`/admin/${key}?status=${status}`} />)}
      </div>}
    {days && <DailyChart days={days} />}
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">Últimos movimientos</h2>
      {!movements?.length ? <p>{movements ? "No hay movimientos registrados." : "No se pudieron cargar los movimientos."}</p> :
        <div className="admin-table-scroll"><table>
          <thead><tr>{["Fecha", "Tipo", "Servicio", "Cliente", "Proveedor", "Monto", "Estado"].map((title) => <th key={title} scope="col">{title}</th>)}</tr></thead>
          <tbody>{movements.map((entry) => <tr key={entry.id}>
            <td>{adminDate(entry.at)}</td><td>{movementLabel[entry.kind]}</td>
            <td>{entry.service_id ? <Link href={`/admin/servicios?detail=${entry.service_id}`} className="underline">{entry.service_id}</Link> : "—"}</td>
            <td>{[entry.first_name, entry.last_name].filter(Boolean).join(" ") || "—"}</td><td>{entry.provider ?? "—"}</td>
            <td>{money(entry.amount)}</td><td><StatusBadge status={entry.status} label={entry.status === "released" ? "Liberado" : undefined} /></td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </main>;
}

function DailyChart({ days }: { days: FinanceDay[] }) {
  const peak = Math.max(1, ...days.map((day) => Number(day.collected)));
  const step = 600 / Math.max(1, days.length);
  return <section className="admin-card">
    <h2 className="text-xl font-semibold">Recaudación y comisiones diarias</h2>
    <p>Azul: recaudado · Naranja: comisiones</p>
    <svg viewBox="0 0 600 135" role="img" aria-label="Gráfico diario de recaudación y comisiones">
      <line x1="0" y1="134" x2="600" y2="134" stroke="var(--lp-line)" />
      {days.map((day, index) => {
        const gross = Number(day.collected) * 130 / peak;
        const commission = Number(day.commission) * 130 / peak;
        return <g key={day.day}>
          <title>{`${day.day}: ${money(day.collected)} recaudado, ${money(day.commission)} comisión`}</title>
          <rect x={index * step} y={134 - gross} width={step * .43} height={gross} fill="var(--lp-ink)" />
          <rect x={index * step + step * .47} y={134 - commission} width={step * .43} height={commission} fill="var(--lp-action)" />
        </g>;
      })}
    </svg>
    <div className="flex justify-between text-sm"><span>{days[0]?.day}</span><span>{days.at(-1)?.day}</span></div>
  </section>;
}
