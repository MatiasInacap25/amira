"use client";

import { useEffect, useId, useRef } from "react";
import Link from "next/link";
import type { ServiceSameDayConflict } from "@/lib/marketplace-api";
import { formatServiceDateTime } from "@/lib/service-status";

type Props = {
  open: boolean;
  conflicts: ServiceSameDayConflict[];
  // Display names by driver id; a conflict whose driver is unknown is labelled generically.
  driverNames: Map<string, string>;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

const UNKNOWN_DRIVER_LABEL = "Conductor";

// Controlled native dialog: the parent decides when it is open, Escape and the cancel button both call onCancel.
export function SameDayConflictDialog({ open, conflicts, driverNames, busy, onConfirm, onCancel }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="quote-dialog same-day-conflict-dialog"
      onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}
      ref={dialogRef}
    >
      <div className="quote-dialog-header">
        <div>
          <p className="eyebrow">ASIGNACIÓN</p>
          <h2 id={titleId}>Conductores con otro servicio el mismo día</h2>
        </div>
      </div>
      <div className="same-day-conflict-body">
        <p id={descriptionId}>
          Los siguientes conductores ya tienen un servicio programado para el mismo día. Puedes asignarlos de todos modos.
        </p>
        <ul className="same-day-conflict-list">
          {conflicts.map((conflict) => (
            <li key={`${conflict.driverId}-${conflict.serviceId}`}>
              <strong>{driverNames.get(conflict.driverId) ?? UNKNOWN_DRIVER_LABEL}</strong>
              <span>{formatServiceDateTime(conflict.serviceAt)}</span>
              <Link href={`/cuenta/servicios/${encodeURIComponent(conflict.serviceId)}`}>Ver servicio</Link>
            </li>
          ))}
        </ul>
        <div className="quote-dialog-actions">
          <button className="button button-secondary" disabled={busy} onClick={onCancel} type="button">Revisar asignación</button>
          <button className="button button-primary" disabled={busy} onClick={onConfirm} type="button">
            {busy ? "Asignando…" : "Asignar de todos modos"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
