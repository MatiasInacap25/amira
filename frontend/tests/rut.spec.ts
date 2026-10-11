import { expect, test } from "@playwright/test";
import { cleanRut, formatRut, isValidRut, normalizeRut } from "../src/lib/validation/rut";

test("cleanRut keeps only digits and a check digit in uppercase", () => {
  expect(cleanRut("12.345.678-k")).toBe("12345678K");
  expect(cleanRut(" 12 345 678 - 5 ")).toBe("123456785");
});

test("normalizeRut returns the API form for valid RUTs in any spelling", () => {
  expect(normalizeRut("12.345.678-5")).toBe("12345678-5");
  expect(normalizeRut("12345678-5")).toBe("12345678-5");
  expect(normalizeRut("76.123.456-0")).toBe("76123456-0");
  expect(normalizeRut("7.123.456-8")).toBe("7123456-8");
  expect(normalizeRut("7.123.456-k")).toBeNull();
});

test("normalizeRut rejects a wrong check digit, malformed bodies and empty input", () => {
  expect(normalizeRut("12.345.678-6")).toBeNull();
  expect(normalizeRut("123456-7")).toBeNull();
  expect(normalizeRut("123456789-5")).toBeNull();
  expect(normalizeRut("12.345.678-")).toBeNull();
  expect(normalizeRut("")).toBeNull();
});

test("a K check digit is accepted only when it is the computed one", () => {
  expect(isValidRut("5.500.000-K")).toBe(true);
  expect(isValidRut("5.500.000-0")).toBe(false);
});

test("formatRut returns the display form for valid RUTs and null otherwise", () => {
  expect(formatRut("123456785")).toBe("12.345.678-5");
  expect(formatRut("76123456-0")).toBe("76.123.456-0");
  expect(formatRut("12345678-6")).toBeNull();
});
