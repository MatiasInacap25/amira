"use client";

import { useState, type FormEvent } from "react";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import {
  PHONE_CHANGE_PATH,
  normalizePhone,
  phoneChangeError,
  phoneInputError,
  replacedPhoneFactorIds,
} from "@/lib/phone-change";
import { currentAccessToken } from "@/lib/provider-request-access";
import { createClient } from "@/lib/supabase/client";

export type ChangedAccount = { phone: string | null };

const INVALID_CODE_ERRORS = new Set(["mfa_verification_failed", "mfa_challenge_expired", "mfa_verification_rejected"]);

function smsErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : "";
  const code = typeof (error as { code?: unknown } | null)?.code === "string" ? (error as { code: string }).code : "";
  if (INVALID_CODE_ERRORS.has(code) || /invalid.*code|verification|challenge|expired/i.test(raw)) return "El código no es válido o venció. Solicita otro código e inténtalo nuevamente.";
  if (/rate limit|too many requests/i.test(raw)) return "Hubo demasiados intentos. Espera un momento antes de volver a probar.";
  if (/already exists|phone.*(taken|in use)/i.test(raw)) return "Ese número ya está registrado en tu cuenta.";
  return "No pudimos enviar el código SMS. Inténtalo nuevamente.";
}

export function PhoneChangeForm({
  currentPhone,
  onChanged,
  onCancel,
}: {
  currentPhone: string | null;
  onChanged: (account: ChangedAccount, warning: string | null) => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [factorId, setFactorId] = useState<string | null>(null);
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendCode(id: string) {
    const { data, error: challengeError } = await createClient().auth.mfa.challenge({ factorId: id });
    if (challengeError) throw challengeError;
    setChallengeId(data.id);
  }

  async function submitPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const inputError = phoneInputError(phone, currentPhone);
    setError(inputError ?? "");
    if (inputError) return;
    setBusy(true);
    try {
      // Supabase requires a distinct friendly name per factor; the registration factor is "Amira SMS".
      const { data, error: enrollError } = await createClient().auth.mfa.enroll({
        factorType: "phone", phone: normalizePhone(phone), friendlyName: `Amira SMS ${Date.now()}`,
      });
      if (enrollError) throw enrollError;
      setFactorId(data.id);
      await sendCode(data.id);
      setStep("code");
    } catch (cause) {
      setError(smsErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (busy || !factorId) return;
    setBusy(true);
    setError("");
    try {
      await sendCode(factorId);
    } catch (cause) {
      setError(smsErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !factorId || !challengeId) return;
    if (!/^\d{6}$/.test(code.trim())) {
      setError("Ingresa el código de 6 dígitos que te enviamos por SMS.");
      return;
    }
    setBusy(true);
    setError("");
    const supabase = createClient();
    try {
      const { error: verifyError } = await supabase.auth.mfa.verify({ factorId, challengeId, code: code.trim() });
      if (verifyError) {
        setError(smsErrorMessage(verifyError));
        return;
      }
      const token = await currentAccessToken();
      const response = await authenticatedApiFetch(PHONE_CHANGE_PATH, token, process.env.NEXT_PUBLIC_API_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ factor_id: factorId, phone: normalizePhone(phone) }),
      });
      if (!response.ok) {
        setError(await phoneChangeError(response));
        return;
      }
      const account = await response.json() as ChangedAccount;
      // The old number stops receiving the sign-in SMS; a failure here leaves it as a second factor, never locks the user out.
      let warning: string | null = null;
      const { data: factors, error: listError } = await supabase.auth.mfa.listFactors();
      const replaced = listError ? [] : replacedPhoneFactorIds(factors.all, factorId);
      const removals = await Promise.all(replaced.map((id) => supabase.auth.mfa.unenroll({ factorId: id })));
      if (listError || removals.some((result) => result.error)) {
        warning = "Guardamos tu número nuevo, pero no pudimos quitar el anterior de la verificación SMS. Vuelve a intentarlo más tarde.";
      }
      onChanged(account, warning);
    } catch {
      setError("No pudimos guardar el número. Inténtalo nuevamente.");
    } finally {
      setBusy(false);
    }
  }

  // An abandoned, unverified factor is removed so it never shows up at sign-in.
  async function cancel() {
    if (factorId) await createClient().auth.mfa.unenroll({ factorId }).catch(() => undefined);
    onCancel();
  }

  return (
    <div className="phone-change">
      {error && <p role="alert" aria-live="assertive" className="auth-error">{error}</p>}
      {step === "phone" ? (
        <form aria-label="Cambiar teléfono" className="auth-form" noValidate onSubmit={submitPhone}>
          <label className="auth-field" htmlFor="new-phone">Número nuevo
            <input autoComplete="tel" id="new-phone" inputMode="tel" maxLength={32} onChange={(event) => setPhone(event.target.value)} placeholder="+56912345678" type="tel" value={phone} />
          </label>
          <p className="auth-help">Te enviaremos un código por SMS a ese número para confirmarlo.</p>
          <div className="phone-change-actions">
            <button className="auth-submit" disabled={busy} type="submit">{busy ? "Enviando…" : "Enviar código"}</button>
            <button className="button button-secondary" disabled={busy} onClick={() => void cancel()} type="button">Cancelar</button>
          </div>
        </form>
      ) : (
        <form aria-label="Confirmar teléfono" className="auth-form" noValidate onSubmit={submitCode}>
          <p className="auth-help">Enviamos un código a {normalizePhone(phone)}.</p>
          <label className="auth-field" htmlFor="new-phone-code">Código SMS
            <input autoComplete="one-time-code" id="new-phone-code" inputMode="numeric" maxLength={6} onChange={(event) => setCode(event.target.value)} value={code} />
          </label>
          <div className="phone-change-actions">
            <button className="auth-submit" disabled={busy} type="submit">{busy ? "Verificando…" : "Confirmar número"}</button>
            <button className="button button-secondary" disabled={busy} onClick={() => void resend()} type="button">Reenviar código</button>
            <button className="button button-secondary" disabled={busy} onClick={() => void cancel()} type="button">Cancelar</button>
          </div>
        </form>
      )}
    </div>
  );
}
