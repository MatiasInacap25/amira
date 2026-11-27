"use client";

import { useState } from "react";
import { toast } from "sonner";
import { downloadAdminCsv } from "@/lib/admin/client";

export function FinanceExport({ query }: { query: string }) {
  const [pending, setPending] = useState(false);
  return <button type="button" className="admin-button" disabled={pending} onClick={async () => {
    setPending(true);
    try { await downloadAdminCsv(`/api/admin/finance/export.csv?${query}`, "comisiones"); }
    catch { toast.error("No se pudo exportar el archivo."); }
    finally { setPending(false); }
  }}>Exportar CSV</button>;
}

export function DashboardPeriod({ period }: { period: { preset: string; from: string; to: string } }) {
  const [preset, setPreset] = useState(period.preset);
  return <form action="/admin" className="admin-card admin-toolbar">
    <label className="grid gap-1">Período
      <select name="period" className="admin-input" value={preset} onChange={(event) => setPreset(event.target.value)}>
        <option value="today">Hoy</option><option value="week">7 días</option><option value="30">30 días</option>
        <option value="month">Mes actual</option><option value="custom">Rango personalizado</option>
      </select>
    </label>
    {preset === "custom" && <>
      <label className="grid gap-1">Desde<input type="date" name="from" defaultValue={period.from} required className="admin-input" /></label>
      <label className="grid gap-1">Hasta<input type="date" name="to" defaultValue={period.to} required className="admin-input" /></label>
    </>}
    <button className="admin-button admin-primary">Aplicar</button>
  </form>;
}
