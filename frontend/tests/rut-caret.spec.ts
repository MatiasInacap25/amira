import { expect, test } from "@playwright/test";
import { caretForSignificant, countRutSignificant } from "../src/lib/validation/rut-caret";

test("countRutSignificant counts digits and k/K before the caret", () => {
  expect(countRutSignificant("12345678-5", 9)).toBe(8);
  expect(countRutSignificant("12.345.678-5", 4)).toBe(3);
  expect(countRutSignificant("5500000-k", 9)).toBe(8);
  expect(countRutSignificant("5500000-K", 0)).toBe(0);
});

test("caretForSignificant places the caret right after the count-th significant character", () => {
  expect(caretForSignificant("12345678-5", 8)).toBe(8);
  expect(caretForSignificant("1234567-8", 3)).toBe(3);
  expect(caretForSignificant("1234567-8", 8)).toBe(9);
  expect(caretForSignificant("5500000-K", 8)).toBe(9);
});

test("caretForSignificant returns 0 for a zero count and masked.length for an overflowing count", () => {
  expect(caretForSignificant("1234567-8", 0)).toBe(0);
  expect(caretForSignificant("", 0)).toBe(0);
  expect(caretForSignificant("1234567-8", 99)).toBe(9);
});

test("editing in the middle keeps the caret after the inserted digit", () => {
  // The field shows "1-2"; the user types "3" after the first digit, so the raw value is "13-2" with the caret at 2.
  const raw = "13-2";
  const caret = 2;
  const significant = countRutSignificant(raw, caret);
  expect(significant).toBe(2);
  expect(caretForSignificant("13-2", significant)).toBe(2);

  // A digit typed at position 1 of "12345678-5" yields raw "192345678-5" with the caret after "19".
  const rawMiddle = "192345678-5";
  expect(countRutSignificant(rawMiddle, 2)).toBe(2);
  expect(caretForSignificant("19234567-8", 2)).toBe(2);
});
