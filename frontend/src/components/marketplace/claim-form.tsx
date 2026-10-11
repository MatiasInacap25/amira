"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { CLAIM_REASON_MAX_LENGTH, claimReasonRejection } from "@/lib/service-status";

type Props = {
  initialReason: string;
  disabled: boolean;
  onContinue: (reason: string) => void;
  onCancel: () => void;
};

/** Collects the claim reason. Submitting only validates and hands the trimmed reason to the confirmation step. */
export function ClaimForm({ initialReason, disabled, onContinue, onCancel }: Props) {
  const fieldId = useId();
  const counterId = useId();
  const errorId = useId();
  const [reason, setReason] = useState(initialReason);
  const [error, setError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    const rejection = claimReasonRejection(reason);
    setError(rejection ?? "");
    if (rejection) return;
    onContinue(reason.trim());
  }

  return (
    <form className="account-service-claim-form" noValidate onSubmit={submit}>
      <div className="marketplace-field">
        <label htmlFor={fieldId}>Motivo del reclamo (obligatorio)</label>
        <textarea
          aria-describedby={`${counterId} ${error ? errorId : ""}`.trim()}
          aria-invalid={error ? true : undefined}
          disabled={disabled}
          id={fieldId}
          maxLength={CLAIM_REASON_MAX_LENGTH}
          onChange={(event) => setReason(event.target.value)}
          ref={textareaRef}
          required
          rows={5}
          value={reason}
        />
        <small className="account-service-hint" id={counterId}>
          {Array.from(reason).length} de {CLAIM_REASON_MAX_LENGTH} caracteres
        </small>
      </div>

      {error && <p className="account-service-form-error" id={errorId} role="alert">{error}</p>}

      <div className="account-service-actions">
        <button className="button button-primary" disabled={disabled} type="submit">Continuar</button>
        <button className="button button-secondary" disabled={disabled} onClick={onCancel} type="button">Cancelar</button>
      </div>
    </form>
  );
}
