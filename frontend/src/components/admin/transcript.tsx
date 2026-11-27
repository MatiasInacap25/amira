"use client";

import { useState } from "react";
import { adminRequest } from "@/lib/admin/client";
import { adminDate } from "@/lib/admin/formatters";

type Message = { id: string; sender: string; text: string; created_at: string; attachment_url?: string };
type Page = { items: Message[]; before: string | null };

export function AdminTranscript({ chatId, hasClaim }: { chatId: string; hasClaim: boolean }) {
  const [reason, setReason] = useState("");
  const [required, setRequired] = useState(!hasClaim);
  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function open(before?: string) {
    if (required && reason.trim().length < 10) return;
    setLoading(true);
    setError(null);
    try {
      const response = await adminRequest(`/api/admin/operations/chats/${encodeURIComponent(chatId)}/transcript`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: reason.trim() || null, before }),
      });
      if (response.status === 403) setRequired(true);
      if (!response.ok) {
        const problem = await response.json().catch(() => null);
        throw new Error(typeof problem?.detail === "string" ? problem.detail : "No se pudo abrir la conversación.");
      }
      const next = await response.json() as Page;
      setPage((old) => before && old ? { items: [...next.items, ...old.items], before: next.before } : next);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "No se pudo abrir la conversación.");
    } finally {
      setLoading(false);
    }
  }
  return <section className="admin-card">
    <h3 className="font-semibold">Conversación del servicio</h3>
    {!page && <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); void open(); }}>
      {required && <label className="grid gap-1">Motivo de acceso
        <textarea className="admin-input" required minLength={10} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>}
      <p className="text-sm">Acceso de solo lectura. La consulta queda en auditoría.</p>
      <button type="submit" className="admin-button" disabled={loading}>Abrir conversación</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    {page?.before && <button type="button" className="admin-button" disabled={loading} onClick={() => { void open(page.before ?? undefined); }}>Ver mensajes anteriores</button>}
    {page && (page.items.length ? <ol className="grid gap-3">{page.items.map((message) => <li className="rounded border p-2" key={message.id}>
      <p className="text-sm font-semibold">{message.sender} · {adminDate(message.created_at)}</p>
      <p className="whitespace-pre-wrap break-words">{message.text}</p>
      {message.attachment_url && <a className="underline" href={message.attachment_url} target="_blank" rel="noopener noreferrer">Ver adjunto</a>}
    </li>)}</ol> : <p>No hay mensajes.</p>)}
  </section>;
}
