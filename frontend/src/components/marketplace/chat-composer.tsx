"use client";

import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { ChatRequestError } from "@/lib/chats";
import { CHAT_ATTACHMENT_ACCEPT, chatAttachmentErrorMessage, validateChatAttachment } from "@/lib/chat-attachments";
import { CHAT_MESSAGE_MAX_LENGTH, validateMessageDraft } from "@/lib/chat-quotations";
import { sendChatMessage, uploadChatAttachment } from "@/lib/marketplace-api";
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

// A photo failure without an HTTP status (network error) falls back to the generic upload message.
function attachmentErrorMessage(cause: unknown): string {
  if (cause instanceof ChatRequestError) return chatAttachmentErrorMessage(cause.status, cause.detailMessage);
  return chatAttachmentErrorMessage(0, null);
}

type SelectedPhoto = { file: File; previewUrl: string };

export function ChatComposer({ chatId, onSent }: Props) {
  const [draft, setDraft] = useState("");
  const [photo, setPhotoState] = useState<SelectedPhoto | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  // The ref mirrors the state so the object URL can be revoked on replace and on unmount.
  const photoRef = useRef<SelectedPhoto | null>(null);

  function setPhoto(next: SelectedPhoto | null) {
    if (photoRef.current) URL.revokeObjectURL(photoRef.current.previewUrl);
    photoRef.current = next;
    setPhotoState(next);
  }

  useEffect(() => () => {
    if (photoRef.current) URL.revokeObjectURL(photoRef.current.previewUrl);
  }, []);

  // A rejected pick keeps the previous photo and the draft; nothing is uploaded.
  function selectPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const validation = validateChatAttachment(file);
    if (validation) {
      setError(validation);
      return;
    }
    setError("");
    setPhoto({ file, previewUrl: URL.createObjectURL(file) });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const text = draft.trim();
    const validation = photo && !text ? null : validateMessageDraft(draft);
    if (validation) {
      setError(validation);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const token = await currentAccessToken();
      if (photo) {
        await uploadChatAttachment(token, chatId, photo.file, text || undefined);
      } else {
        await sendChatMessage(token, chatId, text);
      }
      setDraft("");
      setPhoto(null);
      onSent();
    } catch (cause) {
      // The draft and the photo are kept on failure so nothing the user chose is lost.
      setError(photo ? attachmentErrorMessage(cause) : sendErrorMessage(cause));
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

  const canSend = (draft.trim().length > 0 || photo !== null) && !busy;

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
      {photo && (
        <div className="chat-composer-photo">
          {/* A blob URL of the local photo, so next/image optimization does not apply. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="Vista previa de la foto adjunta" className="chat-composer-thumb" src={photo.previewUrl} />
          <button className="button button-secondary" disabled={busy} onClick={() => setPhoto(null)} type="button">
            Quitar
          </button>
        </div>
      )}
      <div className="chat-composer-footer">
        <div className="chat-composer-tools">
          <input accept={CHAT_ATTACHMENT_ACCEPT} hidden onChange={selectPhoto} ref={fileInput} type="file" />
          <button
            className="button button-secondary chat-composer-attach"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
            type="button"
          >
            Adjuntar foto
          </button>
          <p className="chat-composer-count" id="chat-composer-count">
            {draft.length}/{CHAT_MESSAGE_MAX_LENGTH}
          </p>
        </div>
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
