"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ClaimForm } from "@/components/marketplace/claim-form";
import { ClaimWindowCountdown, useClaimWindowClock } from "@/components/marketplace/claim-window-countdown";
import type { ServiceDetail } from "@/lib/marketplace-api";
import { formatServiceDateTime, serviceActionErrorMessage } from "@/lib/service-status";

type Props = {
  service: ServiceDetail;
  consentPending: boolean;
  claimPending: boolean;
  onConsent: () => Promise<unknown>;
  onClaim: (reason: string) => Promise<unknown>;
};

// One step is visible at a time. Every step other than "idle" replaces the trigger buttons.
type Step = "idle" | "consent-confirm" | "claim-form" | "claim-confirm";
type Trigger = "consent" | "claim";

const CONSENT_DONE_MESSAGE = "Registramos tu conformidad. El pago al prestador se liberará en el próximo proceso.";
const CLAIM_DONE_MESSAGE = "Reclamo enviado. El pago al prestador queda retenido mientras se revisa.";

/**
 * Customer resolution of a completed service: the claim window countdown, "Todo conforme" (consent) and "Reclamar" (claim).
 * Both actions confirm before they are sent, because consent releases the payout early and a claim holds it.
 */
export function CustomerServiceActions({ service, consentPending, claimPending, onConsent, onClaim }: Props) {
  const claimWindow = useClaimWindowClock(service.payoutDeadlineAt);
  const [step, setStep] = useState<Step>("idle");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const stepTitleId = useId();
  const stepTitleRef = useRef<HTMLHeadingElement>(null);
  const resultRef = useRef<HTMLParagraphElement>(null);
  const consentButtonRef = useRef<HTMLButtonElement>(null);
  const claimButtonRef = useRef<HTMLButtonElement>(null);
  // Set when a step closes, so focus returns to the control that opened it.
  const returnFocusTo = useRef<Trigger | null>(null);
  const busy = consentPending || claimPending;
  // Set synchronously on the first submit, so a second click before the pending state renders cannot send a request.
  const submitting = useRef(false);

  useEffect(() => {
    if (step === "consent-confirm" || step === "claim-confirm") {
      stepTitleRef.current?.focus();
      return;
    }
    if (step === "idle" && returnFocusTo.current) {
      const trigger = returnFocusTo.current === "consent" ? consentButtonRef : claimButtonRef;
      trigger.current?.focus();
      returnFocusTo.current = null;
    }
  }, [step]);

  useEffect(() => {
    if (result) resultRef.current?.focus();
  }, [result]);

  function openStep(next: Step) {
    setError("");
    setResult("");
    setStep(next);
  }

  function closeStep(trigger: Trigger) {
    returnFocusTo.current = trigger;
    setStep("idle");
  }

  async function confirmConsent() {
    if (busy || submitting.current) return;
    submitting.current = true;
    setError("");
    try {
      await onConsent();
      setResult(CONSENT_DONE_MESSAGE);
      setStep("idle");
    } catch (cause) {
      setError(serviceActionErrorMessage(cause, "consent"));
      closeStep("consent");
    } finally {
      submitting.current = false;
    }
  }

  function continueClaim(value: string) {
    setReason(value);
    openStep("claim-confirm");
  }

  async function confirmClaim() {
    if (busy || submitting.current) return;
    submitting.current = true;
    setError("");
    try {
      await onClaim(reason);
      setReason("");
      setResult(CLAIM_DONE_MESSAGE);
      setStep("idle");
    } catch (cause) {
      // The reason is kept, so the customer can retry from the form without retyping it.
      setError(serviceActionErrorMessage(cause, "claim"));
      closeStep("claim");
    } finally {
      submitting.current = false;
    }
  }

  const deadlineLabel = formatServiceDateTime(service.payoutDeadlineAt);
  // The window and the countdown apply only while the service is completed, not consented and not in a claim.
  const windowOpen = service.status === "completed" && service.customerConsentAt === null && !service.claimOpen;
  // "Reclamar" waits for the client clock: while it is pending or the deadline is missing, the claim is not offered.
  const canClaimNow = windowOpen && service.canClaim && claimWindow.status === "open";

  if (service.status !== "completed" && service.status !== "disputed") return null;

  return (
    <div className="account-service-resolution">
      {service.claimOpen && (
        <p className="account-service-state account-service-state-claim">Reclamo abierto. El pago al prestador queda retenido mientras se revisa.</p>
      )}
      {!service.claimOpen && service.customerConsentAt && (
        <p className="account-service-state account-service-state-consent">
          Conformidad registrada el {formatServiceDateTime(service.customerConsentAt)}. El pago al prestador se liberará en el próximo proceso.
        </p>
      )}

      {windowOpen && <ClaimWindowCountdown claimWindow={claimWindow} deadlineLabel={deadlineLabel} />}

      {step === "idle" && (service.canConsent || canClaimNow) && (
        <div className="account-service-actions">
          {service.canConsent && (
            <button className="button button-primary" disabled={busy} onClick={() => openStep("consent-confirm")} ref={consentButtonRef} type="button">
              Todo conforme
            </button>
          )}
          {canClaimNow && (
            <button className="button button-secondary" disabled={busy} onClick={() => openStep("claim-form")} ref={claimButtonRef} type="button">
              Reclamar
            </button>
          )}
        </div>
      )}

      {step === "consent-confirm" && (
        <section aria-labelledby={stepTitleId} className="account-service-confirm">
          <h3 id={stepTitleId} ref={stepTitleRef} tabIndex={-1}>Confirmar conformidad</h3>
          <p className="account-service-assignment-hint">
            Al confirmar, el pago al prestador se libera antes del plazo. Después no podrás reclamar este servicio.
          </p>
          <div className="account-service-actions">
            <button className="button button-primary" disabled={busy} onClick={() => void confirmConsent()} type="button">
              {consentPending ? "Confirmando…" : "Confirmar conformidad"}
            </button>
            <button className="button button-secondary" disabled={busy} onClick={() => closeStep("consent")} type="button">Cancelar</button>
          </div>
        </section>
      )}

      {step === "claim-form" && (
        <section aria-labelledby={stepTitleId} className="account-service-confirm">
          <h3 id={stepTitleId}>Reclamar el servicio</h3>
          <p className="account-service-assignment-hint">Describe el motivo. Al enviarlo, el pago al prestador queda retenido.</p>
          <ClaimForm disabled={busy} initialReason={reason} onCancel={() => closeStep("claim")} onContinue={continueClaim} />
        </section>
      )}

      {step === "claim-confirm" && (
        <section aria-labelledby={stepTitleId} className="account-service-confirm">
          <h3 id={stepTitleId} ref={stepTitleRef} tabIndex={-1}>Confirmar reclamo</h3>
          <p className="account-service-assignment-hint">Motivo que se enviará:</p>
          <blockquote className="account-service-reason">{reason}</blockquote>
          <div className="account-service-actions">
            <button className="button button-primary" disabled={busy} onClick={() => void confirmClaim()} type="button">
              {claimPending ? "Enviando…" : "Enviar reclamo"}
            </button>
            <button className="button button-secondary" disabled={busy} onClick={() => openStep("claim-form")} type="button">Volver</button>
          </div>
        </section>
      )}

      {error && <p className="account-service-form-error" role="alert">{error}</p>}
      {result && (
        <p className="account-service-result" ref={resultRef} role="status" tabIndex={-1}>{result}</p>
      )}
    </div>
  );
}
