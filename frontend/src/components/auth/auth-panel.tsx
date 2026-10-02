"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Eye, EyeOff, LockKeyhole, Truck } from "lucide-react";
import type { SupabaseClient, User } from "@supabase/supabase-js";
import { accountApiFetch } from "@/lib/auth/account-api";
import { safeNextPath } from "@/lib/auth/safe-next-path";
import { createClient } from "@/lib/supabase/client";

type AuthMode = "login" | "register";
type AuthStep = "loading" | "credentials" | "email-pending" | "enroll" | "verify" | "account";
type AccountRole = "client" | "company_owner" | "independent_driver";
type PhoneFactor = { id: string; phone?: string; status?: string };

const AUTH_ERROR = "No pudimos completar la operación. Revisa los datos e intenta nuevamente.";
const REGISTRATION_DRAFT_KEY = "amira-registration-draft";
type RegistrationDraft = {
  email: string;
  phone: string;
  firstName: string;
  lastName: string;
  nationalId: string;
  birthDate: string;
  role: AccountRole;
  displayName: string;
  companyTaxId: string;
  alsoDriver: boolean;
};

function messageFor(error: unknown) {
  const raw = error instanceof Error ? error.message : "";
  if (raw === "Las contraseñas no coinciden.") return raw;
  if (/invalid login credentials|invalid credentials/i.test(raw)) return "El correo o la contraseña no son correctos.";
  if (/email not confirmed/i.test(raw)) return "Confirma tu correo antes de iniciar sesión. Revisa también la carpeta de correo no deseado.";
  if (/invalid verification code|mfa.*verification|challenge/i.test(raw)) return "El código no es válido o venció. Solicita otro código e inténtalo nuevamente.";
  if (/rate limit|too many requests/i.test(raw)) return "Hubo demasiados intentos. Espera un momento antes de volver a probar.";
  if (/independent driver provisioning is not configured/i.test(raw)) return "El registro de conductor independiente todavía requiere configuración. Contacta al equipo de Amira para continuar.";
  if (/^El registro como conductor vinculado/.test(raw)) return raw;
  if (/API todavía no está configurada correctamente/i.test(raw)) return raw;
  if (/^Confirma tu correo|^La sesión |^Completa la verificación|^Completa tu correo|^Ingresa un número|^La API todavía|^El registro de conductor|^Ya existe una cuenta|^Revisa los campos|^El servicio no está disponible/.test(raw)) return raw;
  return AUTH_ERROR;
}

function isEmailConfirmed(user: User | null | undefined): user is User {
  return Boolean(user && (user.email_confirmed_at || user.confirmed_at));
}

function getSafeNext() {
  if (typeof window === "undefined") return "/servicios";
  return safeNextPath(new URLSearchParams(window.location.search).get("next"));
}

export function AuthPanel({ mode, providerIntent = false }: { mode: AuthMode; providerIntent?: boolean }) {
  const router = useRouter();
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [configError, setConfigError] = useState("");
  const [step, setStep] = useState<AuthStep>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [nationalId, setNationalId] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [factorId, setFactorId] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [code, setCode] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState<AccountRole>(providerIntent ? "independent_driver" : "client");
  const [displayName, setDisplayName] = useState("");
  const [companyTaxId, setCompanyTaxId] = useState("");
  const [alsoDriver, setAlsoDriver] = useState(false);
  const [confirmedUser, setConfirmedUser] = useState<User | null>(null);

  function clearRegistrationValues() {
    setEmail("");
    setPassword("");
    setPasswordConfirm("");
    setPhone("");
    setNationalId("");
    setBirthDate("");
    setFirstName("");
    setLastName("");
    setRole(providerIntent ? "independent_driver" : "client");
    setDisplayName("");
    setCompanyTaxId("");
    setAlsoDriver(false);
    setPhoneVerified(false);
  }

  useEffect(() => {
    let active = true;
    const initializeClient = async () => {
      await Promise.resolve();
      try {
        const supabase = createClient();
        if (active) setClient(supabase);
      } catch {
        if (active) setConfigError("El acceso no está configurado correctamente. Contacta al equipo de Amira.");
      }
    };
    void initializeClient();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const isConfirmationReturn = mode === "register"
      && new URLSearchParams(window.location.search).get("step") === "account";
    if (!isConfirmationReturn || !client) return;

    void (async () => {
      setStep("loading");
      setBusy(true);
      try {
        const { data, error: userError } = await client.auth.getUser();
        if (userError || !isEmailConfirmed(data.user)) {
          setError("Confirma tu correo para continuar con el registro.");
          setStep("credentials");
          return;
        }
        setEmail(data.user.email ?? "");
        try {
          const rawDraft = window.sessionStorage.getItem(REGISTRATION_DRAFT_KEY);
          const draft = rawDraft ? JSON.parse(rawDraft) as RegistrationDraft : null;
          if (draft && draft.email.toLowerCase() === (data.user.email ?? "").toLowerCase()) {
            setPhone(draft.phone);
            setFirstName(draft.firstName);
            setLastName(draft.lastName);
            setNationalId(draft.nationalId);
            setBirthDate(draft.birthDate);
            setRole(draft.role);
            setDisplayName(draft.displayName);
            setCompanyTaxId(draft.companyTaxId);
            setAlsoDriver(draft.alsoDriver);
          } else {
            window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
          }
        } catch {
          window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
        }
        await beginSecondFactor(client, data.user);
      } catch (cause) {
        setError(messageFor(cause));
        setStep("credentials");
      } finally {
        setBusy(false);
      }
    })();
    // Initialization intentionally runs once per route; beginSecondFactor uses current state setters only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, client]);

  async function beginSecondFactor(supabase: SupabaseClient, user: User) {
    if (!isEmailConfirmed(user)) {
      await supabase.auth.signOut();
      throw new Error("Confirma tu correo antes de continuar.");
    }
    setConfirmedUser(user);
    const { data, error: factorsError } = await supabase.auth.mfa.listFactors();
    if (factorsError) throw factorsError;
    const phoneFactors = data.phone as PhoneFactor[];
    const factor = phoneFactors.find((item) => item.status === "verified") ?? phoneFactors[0];
    if (!factor) {
      setStep("enroll");
      setNotice("Protege tu cuenta con un código de seguridad por SMS.");
      return;
    }
    setFactorId(factor.id);
    setPhoneVerified(factor.status === "verified");
    if (factor.phone) setPhone(factor.phone);
    await issueChallenge(supabase, factor.id);
  }

  async function issueChallenge(supabase: SupabaseClient, id: string) {
    setError("");
    const { data, error: challengeError } = await supabase.auth.mfa.challenge({ factorId: id });
    if (challengeError) throw challengeError;
    setChallengeId(data.id);
    setCode("");
    setStep("verify");
    setNotice("Enviamos un código de verificación por SMS.");
  }

  async function handleCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "register") {
        if (password !== passwordConfirm) throw new Error("Las contraseñas no coinciden.");
        const registrationDraft: RegistrationDraft = {
          email: email.trim(), phone: phone.trim(), firstName: firstName.trim(), lastName: lastName.trim(),
          nationalId: nationalId.trim(), birthDate, role, displayName: displayName.trim(),
          companyTaxId: companyTaxId.trim(), alsoDriver,
        };
        window.sessionStorage.setItem(REGISTRATION_DRAFT_KEY, JSON.stringify(registrationDraft));
        const callback = new URL("/auth/callback", window.location.origin);
        callback.searchParams.set("next", providerIntent ? "/registro?step=account&intent=provider" : "/registro?step=account");
        const { data, error: signupError } = await client.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: callback.toString() },
        });
        if (signupError) throw signupError;
        setPassword("");
        setPasswordConfirm("");
        if (data.session) {
          const { data: verified, error: verifyError } = await client.auth.getUser();
          if (verifyError || !isEmailConfirmed(verified.user)) {
            await client.auth.signOut();
            window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
            clearRegistrationValues();
            throw new Error("Confirma tu correo antes de continuar.");
          }
          await beginSecondFactor(client, verified.user);
        } else {
          setStep("email-pending");
          setNotice("Te enviamos un correo para confirmar tu dirección. Después podrás completar tu cuenta.");
        }
      } else {
        const { data, error: signinError } = await client.auth.signInWithPassword({ email: email.trim(), password });
        if (signinError) throw signinError;
        const { data: verified, error: verifyError } = await client.auth.getUser();
        const user = verified.user ?? data.user;
        if (verifyError || !isEmailConfirmed(user)) {
          await client.auth.signOut();
          throw new Error("Confirma tu correo antes de continuar.");
        }
        await beginSecondFactor(client, user);
      }
    } catch (cause) {
      setError(messageFor(cause));
      if (mode === "login") setStep("credentials");
    } finally {
      setBusy(false);
    }
  }

  async function handleEnroll(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy) return;
    setBusy(true);
    setError("");
    try {
      const normalizedPhone = phone.replace(/[\s()-]/g, "");
      if (!/^\+[1-9]\d{7,14}$/.test(normalizedPhone)) {
        throw new Error("Ingresa un número internacional con código de país, por ejemplo +56912345678.");
      }
      const { data, error: enrollError } = await client.auth.mfa.enroll({ factorType: "phone", phone: normalizedPhone, friendlyName: "Amira SMS" });
      if (enrollError) throw enrollError;
      setFactorId(data.id);
      await issueChallenge(client, data.id);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function fetchAccount(accessToken: string) {
    return accountApiFetch("/api/account/me", accessToken, process.env.NEXT_PUBLIC_API_URL);
  }

  async function completeAuthentication(supabase: SupabaseClient) {
    const { data: assurance, error: assuranceError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (assuranceError) throw assuranceError;
    if (assurance.currentLevel !== "aal2") throw new Error("La verificación SMS todavía no está completa. Intenta nuevamente.");
    const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
    if (sessionError || !sessionData.session?.access_token) throw sessionError ?? new Error("La sesión expiró. Inicia sesión nuevamente.");
    const accountResponse = await fetchAccount(sessionData.session.access_token);
    if (accountResponse.status === 404) {
      setStep("account");
      setNotice("Tu correo está confirmado y el teléfono verificado. Completa los datos de tu cuenta.");
      return;
    }
    if (!accountResponse.ok) {
      if (accountResponse.status === 403) throw new Error("La API todavía no reconoce la verificación SMS. Vuelve a iniciar sesión e intenta otra vez.");
      throw new Error("No pudimos comprobar tu cuenta. Intenta nuevamente en unos minutos.");
    }
    router.replace(getSafeNext());
  }

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy || !factorId || !challengeId) return;
    setBusy(true);
    setError("");
    try {
      const { error: verifyError } = await client.auth.mfa.verify({ factorId, challengeId, code: code.trim() });
      if (verifyError) throw verifyError;
      setPhoneVerified(true);
      await completeAuthentication(client);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleProvision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy || !isEmailConfirmed(confirmedUser)) return;
    setBusy(true);
    setError("");
    try {
      const { data: verified, error: verifyError } = await client.auth.getUser();
      if (verifyError || !isEmailConfirmed(verified.user) || verified.user.id !== confirmedUser.id) {
        await client.auth.signOut();
        window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
        setConfirmedUser(null);
        setStep("credentials");
        clearRegistrationValues();
        throw new Error("La sesión no corresponde a un correo confirmado. Inicia sesión nuevamente.");
      }
      const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
      if (assuranceError || assurance.currentLevel !== "aal2") throw new Error("Completa la verificación SMS antes de crear tu cuenta.");
      const { data: sessionData, error: sessionError } = await client.auth.getSession();
      if (sessionError || !sessionData.session?.access_token) throw sessionError ?? new Error("La sesión expiró. Inicia sesión nuevamente.");
      const payload: Record<string, string | boolean> = {
        role,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        national_id: nationalId.trim(),
        birth_date: birthDate,
        phone: phone.trim(),
      };
      if (role !== "client") payload.display_name = displayName.trim();
      if (role === "company_owner") payload.company_tax_id = companyTaxId.trim();
      if (role === "company_owner") payload.also_driver = alsoDriver;
      const response = await accountApiFetch("/api/account/provision", sessionData.session.access_token, process.env.NEXT_PUBLIC_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let detail = "No pudimos crear tu cuenta. Revisa los datos e intenta nuevamente.";
        try {
          const body = await response.json() as { detail?: string };
          if (response.status === 503 && role === "independent_driver") {
            detail = "El registro de conductor independiente todavía requiere configuración. Contacta al equipo de Amira para continuar.";
          } else if (response.status === 503 && role === "company_owner" && alsoDriver) {
            detail = "El registro como conductor vinculado todavía requiere configuración. La cuenta de empresa puede continuar sin activar esa opción.";
          } else if (response.status === 409) {
            detail = "Ya existe una cuenta con datos distintos para este correo. Contacta al equipo de Amira para revisarlo.";
          } else if (response.status === 422) {
            detail = "Revisa los campos requeridos y vuelve a intentarlo.";
          } else if (typeof body.detail === "string" && response.status >= 500) {
            detail = "El servicio no está disponible por el momento. Intenta nuevamente más tarde.";
          }
        } catch { /* Keep the safe generic message for non-JSON failures. */ }
        throw new Error(detail);
      }
      window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
      router.replace(getSafeNext());
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    if (!client) return;
    setBusy(true);
    try {
      await client.auth.signOut();
      window.sessionStorage.removeItem(REGISTRATION_DRAFT_KEY);
      setConfirmedUser(null);
      clearRegistrationValues();
      setStep("credentials");
      setNotice("Cerraste tu sesión de forma segura.");
      router.replace(mode === "register" ? "/registro" : "/login");
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  const title = step === "loading" ? "Cargando tu sesión" : step === "email-pending" ? "Confirma tu correo" : step === "enroll" ? "Verifica tu teléfono" : step === "verify" ? "Ingresa tu código SMS" : step === "account" ? "Completa tu cuenta" : mode === "login" ? "Qué bueno verte" : "Crea tu cuenta";

  return (
    <main className="auth-shell">
      <section aria-label="Amira, acceso a tu cuenta" className="auth-brand-panel">
        <Link aria-label="Amira, volver al inicio" className="auth-brand" href="/">
          <span className="auth-brand-mark"><Truck aria-hidden="true" size={22} /></span>
          <span>amira<span>.</span></span>
        </Link>
        <div className="auth-brand-copy">
          <p className="auth-kicker">CONECTA. COTIZA. COORDINA.</p>
          <h1>El movimiento empieza con una cuenta segura.</h1>
          <p>Encuentra servicios de transporte o prepara tu perfil para ofrecerlos, con la confianza de verificar cada acceso.</p>
        </div>
        <div className="auth-brand-foot"><LockKeyhole aria-hidden="true" size={17} /><span>Tu seguridad también es parte del viaje.</span></div>
      </section>

      <section className="auth-form-panel">
        <div className="auth-form-wrap">
          <Link className="auth-back-link" href="/"><ArrowLeft aria-hidden="true" size={15} /> Volver a Amira</Link>
          <div className="auth-heading">
            <p className="auth-kicker">{step === "account" ? "UN ÚLTIMO PASO" : step === "verify" || step === "enroll" ? "SEGURIDAD DE LA CUENTA" : "TRANSPORTE, MÁS CERCA"}</p>
            <h2>{title}</h2>
            <p>{step === "account" ? "Estos datos crean tu cuenta de Amira; no se envían a Supabase como metadatos de autorización." : step === "email-pending" ? "Te enviaremos a este mismo flujo después de confirmar el correo." : step === "enroll" || step === "verify" ? `Cuenta: ${email || confirmedUser?.email || "correo confirmado"}` : mode === "login" ? "Ingresa para continuar donde quedaste." : "Regístrate con tu correo y confirma la dirección antes de completar tu perfil."}</p>
          </div>

          {notice && <p aria-live="polite" className="auth-notice" role="status">{notice}</p>}
          {(error || configError) && <p aria-live="assertive" className="auth-error" role="alert">{error || configError}</p>}

          {step === "loading" && <p aria-live="polite" className="auth-loading" role="status">Verificando el estado de tu correo y sesión…</p>}
          {step === "credentials" && !client && !configError && <p aria-live="polite" className="auth-loading" role="status">Preparando el acceso seguro…</p>}
          {step === "credentials" && (
            <form className="auth-form" onSubmit={handleCredentials}>
              {mode === "register" && <>
                <div className="auth-name-fields">
                  <label className="auth-field" htmlFor="auth-first-name">Nombre
                    <input autoComplete="given-name" id="auth-first-name" maxLength={120} onChange={(event) => setFirstName(event.target.value)} required value={firstName} />
                  </label>
                  <label className="auth-field" htmlFor="auth-last-name">Apellido
                    <input autoComplete="family-name" id="auth-last-name" maxLength={120} onChange={(event) => setLastName(event.target.value)} required value={lastName} />
                  </label>
                </div>
                <label className="auth-field" htmlFor="auth-phone">Teléfono móvil
                  <input autoComplete="tel" id="auth-phone" inputMode="tel" onChange={(event) => setPhone(event.target.value)} placeholder="+56912345678" required type="tel" value={phone} />
                  <span className="auth-help">Incluye el código de país. Este número también se verificará por SMS.</span>
                </label>
                <label className="auth-field" htmlFor="auth-national-id">RUT personal
                  <input autoComplete="off" id="auth-national-id" maxLength={16} onChange={(event) => setNationalId(event.target.value)} placeholder="12.345.678-5" required value={nationalId} />
                </label>
                <label className="auth-field" htmlFor="auth-birth-date">Fecha de nacimiento
                  <input autoComplete="bday" id="auth-birth-date" max={new Date().toISOString().slice(0, 10)} min="1900-01-01" onChange={(event) => setBirthDate(event.target.value)} required type="date" value={birthDate} />
                </label>
                {providerIntent && <>
                  <label className="auth-field" htmlFor="auth-provider-role">Quiero ofrecer mis servicios como
                    <select id="auth-provider-role" onChange={(event) => setRole(event.target.value as AccountRole)} value={role}>
                      <option value="independent_driver">Conductor independiente</option>
                      <option value="company_owner">Empresa transportista</option>
                    </select>
                  </label>
                  {role === "company_owner" && <>
                    <label className="auth-field" htmlFor="auth-company-tax-id">RUT de la empresa
                      <input autoComplete="off" id="auth-company-tax-id" maxLength={16} onChange={(event) => setCompanyTaxId(event.target.value)} required value={companyTaxId} />
                    </label>
                    <label className="auth-checkbox" htmlFor="auth-also-driver">
                      <input checked={alsoDriver} id="auth-also-driver" onChange={(event) => setAlsoDriver(event.target.checked)} type="checkbox" />
                      También quiero registrarme como conductor de mi propia empresa para reservar servicios.
                    </label>
                  </>}
                </>}
              </>}
              <label className="auth-field" htmlFor="auth-email">Correo electrónico
                <input autoComplete="email" id="auth-email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
              </label>
              <div className="auth-field">
                <label htmlFor="auth-password">Contraseña</label>
                <span className="auth-password-wrap">
                  <input autoComplete={mode === "login" ? "current-password" : "new-password"} id="auth-password" minLength={8} onChange={(event) => setPassword(event.target.value)} required type={passwordVisible ? "text" : "password"} value={password} />
                  <button aria-label={passwordVisible ? "Ocultar contraseña" : "Mostrar contraseña"} className="auth-reveal" onClick={() => setPasswordVisible((visible) => !visible)} type="button">{passwordVisible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</button>
                </span>
                <span className="auth-help">Usa al menos 8 caracteres. Puedes usar tu gestor de contraseñas.</span>
              </div>
              {mode === "register" && <label className="auth-field" htmlFor="auth-password-confirm">Confirmar contraseña
                <input autoComplete="new-password" id="auth-password-confirm" minLength={8} onChange={(event) => setPasswordConfirm(event.target.value)} required type={passwordVisible ? "text" : "password"} value={passwordConfirm} />
              </label>}
              <button className="auth-submit" disabled={busy || !client} type="submit">{busy ? "Procesando…" : mode === "login" ? "Iniciar sesión" : "Crear cuenta"}<ArrowRight aria-hidden="true" size={17} /></button>
            </form>
          )}

          {step === "email-pending" && <div className="auth-step-actions"><p>Cuando confirmes el correo, volverás aquí para configurar la verificación por SMS y completar tus datos.</p><button className="auth-secondary-action" disabled={busy} onClick={() => { setStep("credentials"); setNotice(""); }} type="button">Volver al acceso</button></div>}

          {step === "enroll" && (
            <form className="auth-form" onSubmit={handleEnroll}>
              <label className="auth-field" htmlFor="auth-phone">Número de teléfono móvil
                <input autoComplete="tel" id="auth-phone" inputMode="tel" onChange={(event) => setPhone(event.target.value)} placeholder="+56912345678" required type="tel" value={phone} />
                <span className="auth-help">Incluye el código de país, por ejemplo +56 para Chile.</span>
              </label>
              <button className="auth-submit" disabled={busy} type="submit">{busy ? "Enviando…" : "Enviar código SMS"}<ArrowRight aria-hidden="true" size={17} /></button>
            </form>
          )}

          {step === "verify" && (
            <form className="auth-form" onSubmit={handleVerify}>
              <label className="auth-field" htmlFor="auth-code">Código de verificación
                <input autoComplete="one-time-code" autoFocus id="auth-code" inputMode="numeric" maxLength={10} onChange={(event) => setCode(event.target.value.replace(/\s/g, ""))} required value={code} />
                <span className="auth-help">El código de un solo uso vence. Nunca lo compartas con otra persona.</span>
              </label>
              <button className="auth-submit" disabled={busy || code.trim().length < 4} type="submit">{busy ? "Verificando…" : "Verificar teléfono"}<ArrowRight aria-hidden="true" size={17} /></button>
              <button className="auth-secondary-action" disabled={busy} onClick={async () => {
                if (!client || !factorId) return;
                setBusy(true);
                try { await issueChallenge(client, factorId); }
                catch (cause) { setError(messageFor(cause)); }
                finally { setBusy(false); }
              }} type="button">Enviar otro código</button>
            </form>
          )}

          {step === "account" && (
            <form className="auth-form" onSubmit={handleProvision}>
              <label className="auth-field" htmlFor="auth-role">¿Cómo usarás Amira?
                <select id="auth-role" onChange={(event) => setRole(event.target.value as AccountRole)} value={role}>
                  {!providerIntent && <option value="client">Buscar un servicio de transporte</option>}
                  <option value="company_owner">Publicar como empresa transportista</option>
                  <option value="independent_driver">Ofrecer servicios como conductor independiente</option>
                </select>
              </label>
              <div className="auth-name-fields">
                <label className="auth-field" htmlFor="auth-first-name">Nombre<input autoComplete="given-name" id="auth-first-name" maxLength={120} onChange={(event) => setFirstName(event.target.value)} required value={firstName} /></label>
                <label className="auth-field" htmlFor="auth-last-name">Apellido<input autoComplete="family-name" id="auth-last-name" maxLength={120} onChange={(event) => setLastName(event.target.value)} required value={lastName} /></label>
              </div>
              <label className="auth-field" htmlFor="auth-account-phone">Teléfono móvil
                <input autoComplete="tel" id="auth-account-phone" inputMode="tel" readOnly={phoneVerified} required type="tel" value={phone} />
                <span className="auth-help">Este es el número que acabas de verificar por SMS.</span>
              </label>
              <label className="auth-field" htmlFor="auth-account-national-id">RUT personal
                <input autoComplete="off" id="auth-account-national-id" maxLength={16} onChange={(event) => setNationalId(event.target.value)} required value={nationalId} />
              </label>
              <label className="auth-field" htmlFor="auth-account-birth-date">Fecha de nacimiento
                <input autoComplete="bday" id="auth-account-birth-date" max={new Date().toISOString().slice(0, 10)} min="1900-01-01" onChange={(event) => setBirthDate(event.target.value)} required type="date" value={birthDate} />
              </label>
              {role !== "client" && <label className="auth-field" htmlFor="auth-display-name">Nombre público del prestador<input autoComplete="organization" id="auth-display-name" maxLength={160} onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></label>}
              {role === "company_owner" && <>
                <label className="auth-field" htmlFor="auth-company-tax-id">RUT de la empresa<input autoComplete="off" id="auth-company-tax-id" maxLength={16} onChange={(event) => setCompanyTaxId(event.target.value)} required value={companyTaxId} /></label>
                <label className="auth-checkbox" htmlFor="auth-account-also-driver">
                  <input checked={alsoDriver} id="auth-account-also-driver" onChange={(event) => setAlsoDriver(event.target.checked)} type="checkbox" />
                  También quiero registrarme como conductor de mi propia empresa para reservar servicios.
                </label>
              </>}
              <button className="auth-submit" disabled={busy} type="submit">{busy ? "Creando cuenta…" : "Completar registro"}<ArrowRight aria-hidden="true" size={17} /></button>
            </form>
          )}

          {(step === "account" || step === "enroll" || step === "verify") && <button className="auth-secondary-action auth-signout" disabled={busy} onClick={() => void handleSignOut()} type="button">Cerrar sesión</button>}
          {step === "credentials" && <p className="auth-switch">{mode === "login" ? "¿Todavía no tienes cuenta?" : "¿Ya tienes una cuenta?"} <Link href={mode === "login" ? "/registro" : "/login"}>{mode === "login" ? "Regístrate" : "Inicia sesión"}</Link></p>}
          {step === "email-pending" && <p className="auth-switch">¿Ya confirmaste tu correo? <Link href="/login">Inicia sesión</Link></p>}
          <p className="auth-privacy">Amira nunca solicita códigos SMS por teléfono o mensaje directo.</p>
        </div>
      </section>
    </main>
  );
}
