// Development-only switch that skips the SMS (phone MFA) step.
// Keep this module free of imports so the node unit tests can load it directly.

// Next.js inlines NEXT_PUBLIC_* values only when read as a literal `process.env.NAME`,
// so the variable is read here and never through a dynamic lookup.
export function isDevSkipSmsMfaEnabled(flag: string | undefined, nodeEnv: string | undefined): boolean {
  return flag === "true" && nodeEnv !== "production";
}

export const devSkipSmsMfa = isDevSkipSmsMfaEnabled(
  process.env.NEXT_PUBLIC_DEV_SKIP_SMS_MFA,
  process.env.NODE_ENV,
);

// An aal1 password session is accepted only while the development switch is active.
export function acceptsAssuranceLevel(
  currentLevel: string | null | undefined,
  devSkip: boolean = devSkipSmsMfa,
): boolean {
  return currentLevel === "aal2" || (devSkip && currentLevel === "aal1");
}
