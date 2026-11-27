import { FinanceExport } from "@/components/admin/finance-controls";
import { monthlyPeriod, type FinanceSummary, type ProviderCommission } from "@/lib/admin/finance";
import { adminMoney } from "@/lib/admin/formatters";
import { adminData, checkAdmin } from "@/lib/admin/server";

const money = (value: number | string) => adminMoney(Number(value));

export default async function FinancePage({ searchParams }: PageProps<"/admin/finanzas">) {
  const access = await checkAdmin();
  if (!access) return null;
  const period = monthlyPeriod((await searchParams).month);
  const query = new URLSearchParams({ from: period.from, to: period.to }).toString();
  const [summary, providers] = await Promise.all([
    adminData<FinanceSummary>(`/api/admin/finance/summary?${query}`, access.accessToken),
    adminData<ProviderCommission[]>(`/api/admin/finance/providers?${query}`, access.accessToken),
  ]);
  return <main className="space-y-6 p-6">
    <header><h1 className="text-2xl font-semibold">Comisiones e IVA</h1><p>Ingreso de Amira y débito fiscal en el modelo de mandato.</p></header>
    <form action="/admin/finanzas" className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1">Mes<input name="month" type="month" defaultValue={period.month} className="admin-input" required /></label>
      <button className="admin-button">Aplicar</button>
      <FinanceExport query={query} />
    </form>
    {!summary ? <p role="alert">No se pudo cargar el resumen mensual.</p> :
      <div className="admin-table-scroll"><table><thead><tr>
        {["Mes", "Comisiones brutas", "Comisiones netas", "IVA de comisiones", "Retenciones netas", "IVA de retenciones", "IVA débito total"].map((title) => <th scope="col" key={title}>{title}</th>)}
      </tr></thead><tbody><tr><th scope="row">{period.month}</th>
        {[summary.commission_gross, summary.commission_net, summary.commission_iva, summary.retained_net, summary.retained_iva, summary.platform_iva]
          .map((amount, index) => <td key={index}>{money(amount)}</td>)}
      </tr></tbody></table></div>}
    <p>Base de cálculo para el F29. Validar con el contador.</p>
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">Comisión por proveedor</h2>
      {!providers?.length ? <p>{providers ? "No hay resultados con estos filtros" : "No se pudieron cargar los proveedores."}</p> :
        <div className="admin-table-scroll"><table><thead><tr>
          {["Proveedor", "N° servicios", "Bruto cobrado", "Comisión", "IVA de la comisión", "Neto pagado"].map((title) => <th scope="col" key={title}>{title}</th>)}
        </tr></thead><tbody>
          {providers.map((row, index) => <tr key={index}>
            <th scope="row">{row.provider}</th><td>{row.services}</td>
            {[row.gross, row.commission, row.commission_iva, row.net_paid].map((value, offset) => <td key={offset}>{money(value)}</td>)}
          </tr>)}
        </tbody></table></div>}
    </section>
  </main>;
}
