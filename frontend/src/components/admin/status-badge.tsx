const labels: Record<string, string> = {
  pending: "Pendiente", in_review: "En revisión", open: "Abierto", active: "Activo",
  approved: "Aprobado", verified: "Verificado", paid: "Pagado", completed: "Completado",
  rejected: "Rechazado", cancelled: "Cancelado", disputed: "En reclamo", blocked: "Bloqueado",
  suspended: "Suspendido", in_progress: "En curso", confirmed: "Confirmado", disabled: "Deshabilitado",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = /^(approved|verified|paid|completed|active)$/.test(status) ? "positive" :
    /^(rejected|cancelled|disputed|blocked|suspended|disabled)$/.test(status) ? "negative" : "neutral";
  return <span className="admin-status" data-tone={tone}>{label ?? labels[status] ?? status}</span>;
}
