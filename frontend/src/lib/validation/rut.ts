// Chilean RUT helpers. Input may be typed in any spelling ("12.345.678-k", "12345678-K", ...).
// The API accepts the normalized form "12345678-K" (body without separators, dash, check digit).

const RUT_BODY_PATTERN = /^\d{7,8}$/;

export function cleanRut(value: string) {
  return value.replace(/[^0-9kK]/g, "").toUpperCase();
}

export function rutCheckDigit(body: string) {
  let sum = 0;
  let multiplier = 2;
  for (let index = body.length - 1; index >= 0; index -= 1) {
    sum += Number(body[index]) * multiplier;
    multiplier = multiplier === 7 ? 2 : multiplier + 1;
  }
  const remainder = 11 - (sum % 11);
  if (remainder === 11) return "0";
  if (remainder === 10) return "K";
  return String(remainder);
}

function parseRut(value: string) {
  const clean = cleanRut(value);
  const body = clean.slice(0, -1);
  const verifier = clean.slice(-1);
  if (!RUT_BODY_PATTERN.test(body) || rutCheckDigit(body) !== verifier) return null;
  return { body, verifier };
}

export function isValidRut(value: string) {
  return parseRut(value) !== null;
}

// Returns "12345678-5" for a valid RUT, or null when the check digit or body is wrong.
export function normalizeRut(value: string) {
  const parsed = parseRut(value);
  return parsed ? `${parsed.body}-${parsed.verifier}` : null;
}

// Maximum significant characters kept by the mask. Generous on purpose: it only bounds unbounded input.
const RUT_MASK_MAX_LENGTH = 12;

// Live input mask: keeps digits and a K (any case) only as the check digit, and inserts the dash before
// the last character, so "123456785" reads "12345678-5" while typing. Extra digits are NOT dropped, so a
// mistyped number such as "1234567855" reads "123456785-5" and stays invalid instead of looking valid.
export function maskRutInput(value: string) {
  const clean = cleanRut(value).slice(0, RUT_MASK_MAX_LENGTH);
  const endsWithK = clean.endsWith("K");
  const digits = clean.replace(/K/g, "");
  const chars = endsWithK ? `${digits}K` : digits;
  return chars.length < 2 ? chars : `${chars.slice(0, -1)}-${chars.slice(-1)}`;
}

// Returns the display form "12.345.678-5" for a valid RUT, or null otherwise.
export function formatRut(value: string) {
  const parsed = parseRut(value);
  if (!parsed) return null;
  const grouped = parsed.body.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${grouped}-${parsed.verifier}`;
}
