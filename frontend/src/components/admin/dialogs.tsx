"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";

function Modal({ title, children, className, onClose }: {
  title: string; children: ReactNode; className: string; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} className={className} aria-labelledby={titleId} onClose={onClose}
      onClick={(event) => { if (event.target === event.currentTarget) ref.current?.close(); }}>
      <div>
        <header className="mb-4 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-xl font-semibold">{title}</h2>
          <button type="button" aria-label="Cerrar" onClick={() => ref.current?.close()}>✕</button>
        </header>
        {children}
      </div>
    </dialog>
  );
}

export function DetailDrawer(props: { title: string; children: ReactNode; onClose: () => void }) {
  return <Modal {...props} className="admin-detail" />;
}

type Confirmation = {
  title: string; consequence: string; pending?: boolean;
  onClose: () => void; onConfirm: (reason?: string) => void;
};

export function ConfirmDialog(props: Confirmation) { return <ConfirmationDialog {...props} />; }
export function ReasonDialog(props: Confirmation) { return <ConfirmationDialog {...props} reasonRequired />; }

function ConfirmationDialog({ title, consequence, pending, onClose, onConfirm, reasonRequired }: Confirmation & { reasonRequired?: boolean }) {
  return (
    <Modal title={title} className="admin-confirm" onClose={onClose}>
      <p>{consequence}</p>
      <form className="mt-4 grid gap-4" onSubmit={(event) => {
        event.preventDefault();
        const reason = event.currentTarget.elements.namedItem("reason") as HTMLTextAreaElement | null;
        const trimmed = reason?.value.trim();
        if (reason && (!trimmed || trimmed.length < 10 || trimmed.length > 500)) {
          reason.setCustomValidity("Escribe un motivo de entre 10 y 500 caracteres.");
          reason.reportValidity();
          return;
        }
        onConfirm(trimmed);
      }}>
        {reasonRequired && <label className="grid gap-1">Motivo
          <textarea name="reason" className="admin-input" minLength={10} maxLength={500} required
            onInput={(event) => event.currentTarget.setCustomValidity("")} />
        </label>}
        <div className="flex justify-end gap-2">
          <button type="button" className="admin-button" onClick={onClose} disabled={pending}>Volver</button>
          <button type="submit" className="admin-button admin-primary" disabled={pending}>Confirmar</button>
        </div>
      </form>
    </Modal>
  );
}
