"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CHAT_ROOT_KEY } from "@/lib/chats";
import { getChatAttachmentUrl } from "@/lib/marketplace-api";
import { currentAccessToken } from "@/lib/provider-request-access";

type Props = {
  chatId: string;
  messageId: string;
  senderName: string;
};

// The server signs links for 300 s, so the cached link is reused for less than that.
const SIGNED_URL_STALE_MS = 240_000;

// Fetches the signed URL only when the photo is shown. Opening it in a new tab shows the full image.
export function ChatAttachmentImage({ chatId, messageId, senderName }: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const photoQuery = useQuery({
    queryKey: [...CHAT_ROOT_KEY, "attachment", chatId, messageId],
    queryFn: async () => getChatAttachmentUrl(await currentAccessToken(), chatId, messageId),
    staleTime: SIGNED_URL_STALE_MS,
    retry: false,
  });

  function retry() {
    setImageFailed(false);
    void photoQuery.refetch();
  }

  if (photoQuery.isPending) {
    return <div className="chat-attachment chat-attachment-placeholder" role="status">Cargando foto…</div>;
  }

  if (photoQuery.isError || imageFailed) {
    return (
      <div className="chat-attachment chat-attachment-error" role="alert">
        <p>No pudimos cargar la foto.</p>
        <button className="button button-secondary" onClick={retry} type="button">Reintentar</button>
      </div>
    );
  }

  return (
    <a className="chat-attachment" href={photoQuery.data.url} rel="noopener noreferrer" target="_blank">
      {/* Signed Supabase URLs are not whitelisted for next/image, so a plain img is used on purpose. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt={`Foto enviada por ${senderName}`} className="chat-attachment-image" onError={() => setImageFailed(true)} src={photoQuery.data.url} />
    </a>
  );
}
