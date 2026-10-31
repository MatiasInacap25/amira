import { maskRutInput } from "@/lib/validation/rut";

// Characters that survive the RUT mask: digits and the check digit K (any case).
const SIGNIFICANT_CHAR = /[0-9kK]/;

// Counts the significant characters (digits and k/K) that sit before the caret position.
export function countRutSignificant(value: string, caret: number) {
  let count = 0;
  for (const char of value.slice(0, caret)) {
    if (SIGNIFICANT_CHAR.test(char)) count += 1;
  }
  return count;
}

// Returns the caret index right after the count-th significant character of the masked value.
export function caretForSignificant(masked: string, count: number) {
  if (count <= 0) return 0;
  let seen = 0;
  for (let index = 0; index < masked.length; index += 1) {
    if (!SIGNIFICANT_CHAR.test(masked[index])) continue;
    seen += 1;
    if (seen === count) return index + 1;
  }
  return masked.length;
}

// Masks the raw input and computes where the caret should land in the masked value.
// Used by the RUT inputs so that editing mid-value keeps the caret next to the edited digit.
export function maskRutWithCaret(raw: string, selectionStart: number | null) {
  const masked = maskRutInput(raw);
  if (selectionStart === null) return { masked, caret: masked.length };
  return { masked, caret: caretForSignificant(masked, countRutSignificant(raw, selectionStart)) };
}

// Restores the caret once React has written the masked value into the input.
// Setting it synchronously would be overwritten by that controlled-value update, so it waits a frame.
export function restoreRutCaret(input: HTMLInputElement, caret: number) {
  requestAnimationFrame(() => input.setSelectionRange(caret, caret));
}
