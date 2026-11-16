// Phone change from the profile page: the new number is enrolled as a Supabase SMS factor, proved with its code, then
// saved by the API, which checks with Supabase that the number really is that verified factor.

export const PHONE_CHANGE_PATH = "/api/account/phone";

const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;
const PHONE_FORMAT_ERROR = "Ingresa un número internacional con código de país, por ejemplo +56912345678.";

export type PhoneFactorSummary = { id: string; factor_type: string; status: string };

export function normalizePhone(value: string): string {
  return value.replace(/[\s()-]/g, "");
}

export function phoneInputError(value: string, currentPhone: string | null): string | null {
  const phone = normalizePhone(value);
  if (!phone) return "Ingresa el número nuevo.";
  if (!PHONE_PATTERN.test(phone)) return PHONE_FORMAT_ERROR;
  if (currentPhone && phone === normalizePhone(currentPhone)) return "Ese ya es tu número actual.";
  return null;
}

// The verified SMS factors the new number replaces; the new factor and unfinished ones are kept.
export function replacedPhoneFactorIds(factors: PhoneFactorSummary[], newFactorId: string): string[] {
  return factors
    .filter((factor) => factor.factor_type === "phone" && factor.status === "verified" && factor.id !== newFactorId)
    .map((factor) => factor.id);
}

// 403 and 422 carry a Spanish detail from the API; anything else gets a fixed message.
export async function phoneChangeError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = typeof body?.detail === "string" ? body.detail : null;
  if ((response.status === 403 || response.status === 422) && detail) return detail;
  if (response.status === 422) return PHONE_FORMAT_ERROR;
  if (response.status === 503) return "No pudimos comprobar el número. Inténtalo más tarde.";
  return "No pudimos guardar el número. Inténtalo nuevamente.";
}
