"use client";

import { useEffect, useRef, type MouseEvent } from "react";
import { splitStrong, TERMS_INTRO, TERMS_SECTIONS, TERMS_TITLE, type TermsBlock, type TermsNumberedItem } from "@/lib/legal/terms";

type Props = {
  open: boolean;
  onClose: () => void;
  onAccept: () => void;
};

// Mounted only while open: each opening starts scrolled to the top, and unmounting returns focus to the trigger.
export function TermsDialog({ open, onClose, onAccept }: Props) {
  if (!open) return null;
  return <TermsDialogContent onAccept={onAccept} onClose={onClose} />;
}

function TermsDialogContent({ onClose, onAccept }: Omit<Props, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => trigger?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      else if (event.key === "Tab") trapFocus(event, dialogRef.current);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) onClose();
  }

  return (
    <div className="terms-dialog-backdrop" onClick={handleBackdropClick}>
      <div aria-labelledby="terms-dialog-title" aria-modal="true" className="terms-dialog" ref={dialogRef} role="dialog" tabIndex={-1}>
        <h2 id="terms-dialog-title">{TERMS_TITLE}</h2>
        <div className="terms-dialog-body">
          <TermsBlocks blocks={TERMS_INTRO} />
          {TERMS_SECTIONS.map((section) => (
            <section aria-labelledby={`terms-${section.id}`} key={section.id}>
              <h3 id={`terms-${section.id}`}>{section.title}</h3>
              <TermsBlocks blocks={section.blocks} />
            </section>
          ))}
        </div>
        <div className="terms-dialog-actions">
          <button className="button button-secondary" onClick={onClose} type="button">Cerrar</button>
          <button className="button button-primary" onClick={onAccept} type="button">Aceptar</button>
        </div>
      </div>
    </div>
  );
}

// Wraps Tab/Shift+Tab inside the dialog and pulls focus back in if it has landed outside (or on the container).
function trapFocus(event: KeyboardEvent, dialog: HTMLElement | null) {
  if (!dialog) return;
  const items = dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  const first = items[0] ?? dialog;
  const last = items[items.length - 1] ?? dialog;
  const active = document.activeElement;
  const forward = !event.shiftKey;
  const wrap = !(active instanceof Node) || !dialog.contains(active) || (forward ? active === last : active === first || active === dialog);
  if (!wrap) return;
  event.preventDefault();
  (forward ? first : last).focus();
}

function Inline({ text }: { text: string }) {
  return <>{splitStrong(text).map((segment, index) => segment.strong ? <strong key={index}>{segment.text}</strong> : <span key={index}>{segment.text}</span>)}</>;
}

function NumberedItem({ item }: { item: TermsNumberedItem }) {
  if (typeof item === "string") return <li><Inline text={item} /></li>;
  return (
    <li>
      <Inline text={item.text} />
      <ul>{item.children.map((child) => <li key={child}><Inline text={child} /></li>)}</ul>
    </li>
  );
}

function TermsBlocks({ blocks }: { blocks: TermsBlock[] }) {
  return (
    <>
      {blocks.map((block, index) => {
        switch (block.type) {
          case "paragraph":
            return <p key={index}><Inline text={block.text} /></p>;
          case "note":
            return <blockquote key={index}><Inline text={block.text} /></blockquote>;
          case "bullets":
            return <ul key={index}>{block.items.map((item) => <li key={item}><Inline text={item} /></li>)}</ul>;
          case "numbered":
            return <ol key={index}>{block.items.map((item, itemIndex) => <NumberedItem item={item} key={itemIndex} />)}</ol>;
          case "table":
            return (
              <div className="terms-dialog-table-wrap" key={index}>
                <table>
                  <thead><tr>{block.head.map((cell) => <th key={cell} scope="col">{cell}</th>)}</tr></thead>
                  <tbody>{block.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}><Inline text={cell} /></td>)}</tr>)}</tbody>
                </table>
              </div>
            );
        }
      })}
    </>
  );
}
