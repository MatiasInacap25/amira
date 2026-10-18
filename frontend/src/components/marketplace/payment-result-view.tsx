"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { SignInPrompt } from "@/components/marketplace/chat-error-state";
import { useNavUserId } from "@/components/marketplace/site-navigation";
import { ChatRequestError, chatHref } from "@/lib/chats";
import { paymentResultState } from "@/lib/chat-quotations";
import { getPaymentStatus } from "@/lib/marketplace-api";
import { currentAccessToken, paymentAccessMessage } from "@/lib/provider-request-access";

// While the provider confirms, the page re-reads the payment every few seconds, up to a fixed number of times.
const PENDING_POLL_INTERVAL_MS = 3_000;
const PENDING_POLL_LIMIT = 20;

type Props = {
  paymentId: string;
  status: string | undefined;
};

export function PaymentResultView({ paymentId, status }: Props) {
  const { userId, pending: sessionPending } = useNavUserId();
  const paymentQuery = useQuery({
    queryKey: ["payments", userId ?? "", paymentId],
    queryFn: async () => getPaymentStatus(await currentAccessToken(), paymentId),
    enabled: Boolean(userId) && Boolean(paymentId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const state = paymentResultState({ quotationStatus: data.quotationStatus, status: data.status });
      return state === "pending" && query.state.dataUpdateCount < PENDING_POLL_LIMIT ? PENDING_POLL_INTERVAL_MS : false;
    },
  });

  if (!paymentId) {
    return (
      <article className="marketplace-state marketplace-empty chat-result" role="status">
        <h1>No encontramos este pago</h1>
        <p>El enlace no tiene la información del pago.</p>
        <Link className="button button-secondary" href="/mensajes">Ver mis mensajes</Link>
      </article>
    );
  }

  const resultPath = `/pagos/resultado?${new URLSearchParams({ paymentId, ...(status ? { status } : {}) })}`;
  if (!sessionPending && !userId) {
    return <SignInPrompt message={paymentAccessMessage("sign-in")} nextPath={resultPath} />;
  }

  if (paymentQuery.isError) {
    const notFound = paymentQuery.error instanceof ChatRequestError && paymentQuery.error.status === 404;
    return (
      <article className="marketplace-state marketplace-empty chat-result" role="alert">
        <h1>{notFound ? "No encontramos este pago" : "No pudimos consultar tu pago"}</h1>
        <p>{notFound ? "Es posible que el enlace sea incorrecto o que no tengas acceso a este pago." : "Revisa tu conexión e inténtalo nuevamente."}</p>
        <div className="chat-result-actions">
          {!notFound && <button className="button button-primary" onClick={() => void paymentQuery.refetch()} type="button">Reintentar</button>}
          <Link className="button button-secondary" href="/mensajes">Ver mis mensajes</Link>
        </div>
      </article>
    );
  }

  const data = paymentQuery.data;
  if (!data || sessionPending) {
    return (
      <article className="marketplace-state marketplace-empty chat-result" role="status">
        <h1>Consultando tu pago…</h1>
      </article>
    );
  }

  const result = paymentResultState({ quotationStatus: data.quotationStatus, status: data.status ?? status });
  const chatLink = <Link className="button button-primary" href={chatHref(data.chatId)}>Volver a la conversación</Link>;

  if (result === "success") {
    return (
      <article className="marketplace-state marketplace-empty chat-result chat-result-success" role="status">
        <h1>Pago recibido</h1>
        <p>Tu servicio quedó confirmado. Puedes seguir la coordinación desde la conversación.</p>
        <div className="chat-result-actions">{chatLink}</div>
      </article>
    );
  }

  if (result === "failure") {
    return (
      <article className="marketplace-state marketplace-empty chat-result chat-result-failure" role="alert">
        <h1>El pago no se completó</h1>
        <p>La cotización no quedó pagada. Si todavía está vigente, puedes intentarlo nuevamente desde la conversación.</p>
        <div className="chat-result-actions">{chatLink}</div>
      </article>
    );
  }

  return (
    <article className="marketplace-state marketplace-empty chat-result chat-result-pending" role="status" aria-live="polite">
      <h1>Estamos confirmando tu pago</h1>
      <p>Esto puede tardar unos segundos. Actualizaremos esta página automáticamente.</p>
      <div className="chat-result-actions">{chatLink}</div>
    </article>
  );
}
