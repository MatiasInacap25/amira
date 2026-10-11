import Link from "next/link";
import { chatAccessMessage } from "@/lib/chats";
import { ProviderRequestAccessError } from "@/lib/provider-request-access";

/** Sign-in or retry notice for a failed chat request. Not-found is handled by the thread view itself. */
export function ChatErrorState({ error, nextPath, onRetry }: { error: unknown; nextPath: string; onRetry: () => void }) {
  if (error instanceof ProviderRequestAccessError) {
    return (
      <div className="marketplace-state">
        <p role="alert">{chatAccessMessage(error.reason)}</p>
        <Link className="button button-primary" href={`/login?next=${encodeURIComponent(nextPath)}`}>Iniciar sesión</Link>
      </div>
    );
  }
  return (
    <div className="marketplace-state marketplace-error" role="alert">
      <p>No pudimos cargar tus mensajes. Inténtalo nuevamente.</p>
      <button className="button button-secondary" onClick={onRetry} type="button">Reintentar</button>
    </div>
  );
}
