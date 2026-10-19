// Development-only switch that skips the SMS (phone MFA) step.
// Keep this module free of imports so the node unit tests can load it directly.

const DEV_SMS_MFA_BYPASS_APP_ENVS = new Set(["development", "local", "test"]);

// Next.js inlines NEXT_PUBLIC_* values only when read as a literal `process.env.NAME`,
// so both variables are read here and never through a dynamic lookup.
// NODE_ENV is not consulted: Vercel always builds with NODE_ENV=production.
export function isDevSkipSmsMfaEnabled(flag: string | undefined, appEnv: string | undefined): boolean {
  if (flag !== "true") return false;
  return DEV_SMS_MFA_BYPASS_APP_ENVS.has((appEnv ?? "").trim().toLowerCase());
}

export const devSkipSmsMfa = isDevSkipSmsMfaEnabled(
  process.env.NEXT_PUBLIC_DEV_SKIP_SMS_MFA,
  process.env.NEXT_PUBLIC_APP_ENV,
);

// An aal1 password session is accepted only while the development switch is active.
export function acceptsAssuranceLevel(
  currentLevel: string | null | undefined,
  devSkip: boolean = devSkipSmsMfa,
): boolean {
  return currentLevel === "aal2" || (devSkip && currentLevel === "aal1");
}
