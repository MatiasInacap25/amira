"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { formatClp } from "@/lib/chat-quotations";
import { formatServiceDateTime } from "@/lib/service-status";
import type { ServiceDocument } from "@/lib/marketplace-api";
import { documentConceptLabel, documentTypeLabel, IVA_RATE_PERCENT } from "@/lib/tax";

type Props = {
  documents: ServiceDocument[] | undefined;
  failed: boolean;
  loading: boolean;
};

export function ServiceDocuments({ documents, failed, loading }: Props) {
  const [openDocument, setOpenDocument] = useState<ServiceDocument | null>(null);

  if (loading) return <p className="account-service-empty">Cargando documentos…</p>;
  if (failed) return <p className="account-service-empty" role="alert">No pudimos cargar los documentos. Inténtalo nuevamente en unos minutos.</p>;
  if (!documents || documents.length === 0) return <p className="account-service-empty">Aún no hay documentos para este servicio.</p>;

  return (
    <>
      <ul className="service-documents">
        {documents.map((item) => (
          <li key={item.id}>
            <strong>{documentTypeLabel(item.type)}</strong>
            <span>Folio {item.folio}</span>
            <span>{formatClp(item.total)}</span>
            <time dateTime={item.issuedAt}>{formatServiceDateTime(item.issuedAt)}</time>
            <button className="button button-secondary" onClick={() => setOpenDocument(item)} type="button">Ver</button>
          </li>
        ))}
      </ul>
      {openDocument && <DocumentReceiptDialog item={openDocument} onClose={() => setOpenDocument(null)} />}
    </>
  );
}

// Mounted only while open. Unmounting returns focus to the "Ver" button that opened it.
function DocumentReceiptDialog({ item, onClose }: { item: ServiceDocument; onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => trigger?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) onClose();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const items = dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? [];
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="terms-dialog-backdrop" onClick={handleBackdropClick}>
      <div
        aria-labelledby="service-document-title"
        aria-modal="true"
        className="document-receipt"
        onKeyDown={handleKeyDown}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <p className="document-receipt-banner">DOCUMENTO SIMULADO · SIN VALIDEZ TRIBUTARIA</p>
        <header className="document-receipt-header">
          <h2 id="service-document-title">{documentTypeLabel(item.type)}</h2>
          <p>Folio N° {item.folio}</p>
        </header>
        <dl className="document-receipt-parties">
          <div>
            <dt>Emisor</dt>
            <dd>{item.issuerName}</dd>
          </div>
          <div>
            <dt>RUT emisor</dt>
            <dd>{item.issuerTaxId}</dd>
          </div>
          <div>
            <dt>Receptor</dt>
            <dd>{item.recipientName}</dd>
          </div>
          <div>
            <dt>RUT receptor</dt>
            <dd>{item.recipientTaxId ?? "No indicado"}</dd>
          </div>
          <div>
            <dt>Fecha</dt>
            <dd>{formatServiceDateTime(item.issuedAt)}</dd>
          </div>
        </dl>
        <p className="document-receipt-concept">{documentConceptLabel(item.type)}</p>
        <dl className="document-receipt-amounts">
          <div>
            <dt>Neto</dt>
            <dd>{formatClp(item.net)}</dd>
          </div>
          <div>
            <dt>IVA {IVA_RATE_PERCENT} %</dt>
            <dd>{formatClp(item.iva)}</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd>{formatClp(item.total)}</dd>
          </div>
        </dl>
        <div className="document-receipt-actions">
          <button className="button button-secondary" onClick={onClose} type="button">Cerrar</button>
          <button className="button button-primary" onClick={() => window.print()} type="button">Imprimir</button>
        </div>
      </div>
    </div>
  );
}
