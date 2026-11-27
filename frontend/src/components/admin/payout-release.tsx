"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { adminRequest } from "@/lib/admin/client";
import { ConfirmDialog } from "./dialogs";

type Release = { due: number; released: number; missing_account: number; missing_payment: number; skipped: number; failed: number };

export function PayoutRelease() {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [summary, setSummary] = useState<Release | null>(null);
  async function release() {
    setPending(true);
    try {
      const response = await adminRequest("/api/admin/transactions/payouts/release", { method: "POST" });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(typeof error?.detail === "string" ? error.detail : "No se pudieron liberar los desembolsos.");
      }
      setSummary(await response.json() as Release);
      setConfirm(false);
      router.refresh();
    } catch (problem) {
      toast.error(problem instanceof Error ? problem.message : "No se pudieron liberar los desembolsos.");
    } finally {
      setPending(false);
    }
  }
  return <>
    <button type="button" className="admin-button admin-primary" onClick={() => setConfirm(true)}>Liberar desembolsos vencidos</button>
    {summary && <section className="admin-card" role="status">
      <h2 className="font-semibold">Resultado de la liberación simulada</h2>
      <p>Vencidos: {summary.due} · Liberados: {summary.released} · Sin cuenta aprobada: {summary.missing_account} · Sin pago aprobado: {summary.missing_payment} · Omitidos: {summary.skipped} · Fallidos: {summary.failed}</p>
    </section>}
    {confirm && <ConfirmDialog title="Liberar desembolsos vencidos"
      consequence="Se procesarán los casos elegibles con el adaptador simulado. No se moverá dinero real."
      pending={pending} onClose={() => { if (!pending) setConfirm(false); }} onConfirm={() => { void release(); }} />}
  </>;
}
