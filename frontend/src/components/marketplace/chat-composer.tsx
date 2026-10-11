"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ChatRequestError } from "@/lib/chats";
import { CHAT_MESSAGE_MAX_LENGTH, validateMessageDraft } from "@/lib/chat-quotations";
import { sendChatMessage } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

type Props = {
  chatId: string;
  onSent: () => void;
};

// Maps a failed send to a Spanish message. The backend's contact-filter detail is shown verbatim.
function sendErrorMessage(cause: unknown): string {
  if (cause instanceof ChatRequestError) {
    if (cause.detailType === "contact_details_blocked" && cause.detailMessage) return cause.detailMessage;
    if (cause.status === 404) return "Esta conversación ya no está disponible.";
  }
  return "No pudimos enviar el mensaje. Revisa tu conexión e inténtalo nuevamente.";
}

export function ChatComposer({ chatId, onSent }: Props) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const validation = validateMessageDraft(draft);
    if (validation) {
      setError(validation);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await sendChatMessage(await currentAccessToken(), chatId, draft.trim());
      setDraft("");
      onSent();
    } catch (cause) {
      // The draft is kept on failure so nothing the user wrote is lost.
      setError(sendErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  // Enter sends; Shift+Enter inserts a line break. IME composition is left alone.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  const canSend = draft.trim().length > 0 && !busy;

  return (
    <form className="chat-composer" onSubmit={submit} noValidate>
      <label className="chat-composer-field" htmlFor="chat-composer-input">
        <span className="sr-only">Escribe un mensaje</span>
        <textarea
          aria-describedby={error ? "chat-composer-error" : "chat-composer-count"}
          aria-invalid={Boolean(error) || undefined}
          id="chat-composer-input"
          maxLength={CHAT_MESSAGE_MAX_LENGTH}
          onChange={(event) => {
            setDraft(event.target.value);
            if (error) setError("");
          }}
          onKeyDown={handleKeyDown}
          placeholder="Escribe un mensaje"
          rows={2}
          value={draft}
        />
      </label>
      <div className="chat-composer-footer">
        <p className="chat-composer-count" id="chat-composer-count">
          {draft.length}/{CHAT_MESSAGE_MAX_LENGTH}
        </p>
        <button className="button button-primary chat-composer-send" disabled={!canSend} type="submit">
          {busy ? "Enviando…" : "Enviar"}
        </button>
      </div>
      {error && (
        <p className="chat-composer-error" id="chat-composer-error" role="alert">{error}</p>
      )}
    </form>
  );
}
