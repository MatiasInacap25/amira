import Link from "next/link";
import { chatAccessMessage } from "@/lib/chats";
import { ProviderRequestAccessError } from "@/lib/provider-request-access";

/** Alert with a sign-in link that returns the visitor to nextPath. */
export function SignInPrompt({ message, nextPath }: { message: string; nextPath: string }) {
  return (
    <div className="marketplace-state">
      <p role="alert">{message}</p>
      <Link className="button button-primary" href={`/login?next=${encodeURIComponent(nextPath)}`}>Iniciar sesión</Link>
    </div>
  );
}

/** Sign-in or retry notice for a failed chat request. Not-found is handled by the thread view itself. */
export function ChatErrorState({ error, nextPath, onRetry }: { error: unknown; nextPath: string; onRetry: () => void }) {
  if (error instanceof ProviderRequestAccessError) {
    return <SignInPrompt message={chatAccessMessage(error.reason)} nextPath={nextPath} />;
  }
  return (
    <div className="marketplace-state marketplace-error" role="alert">
      <p>No pudimos cargar tus mensajes. Inténtalo nuevamente.</p>
      <button className="button button-secondary" onClick={onRetry} type="button">Reintentar</button>
    </div>
  );
}
