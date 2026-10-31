import { expect, test } from "@playwright/test";
import { cleanRut, formatRut, isValidRut, maskRutInput, normalizeRut } from "../src/lib/validation/rut";

test("maskRutInput keeps only digits and a k, and inserts the dash while typing", () => {
  expect(maskRutInput("1")).toBe("1");
  expect(maskRutInput("12")).toBe("1-2");
  expect(maskRutInput("123456785")).toBe("12345678-5");
  expect(maskRutInput("12.345.678-5")).toBe("12345678-5");
  expect(maskRutInput("abc12#345 678/5")).toBe("12345678-5");
});

test("maskRutInput accepts a lowercase or uppercase k only as the check digit", () => {
  expect(maskRutInput("5500000k")).toBe("5500000-K");
  expect(maskRutInput("5500000K")).toBe("5500000-K");
  expect(maskRutInput("55k00000")).toBe("550000-0");
  expect(maskRutInput("5k5k")).toBe("55-K");
  expect(maskRutInput("k")).toBe("K");
});

test("maskRutInput keeps every digit typed, even beyond the valid 8-digit body", () => {
  expect(maskRutInput("1234567890")).toBe("123456789-0");
  expect(maskRutInput("123456789k")).toBe("123456789-K");
  expect(maskRutInput("")).toBe("");
});

test("maskRutInput bounds very long input at a generous length", () => {
  expect(maskRutInput("1234567890123456")).toBe("12345678901-2");
});

test("maskRutInput keeps extra digits so a mistyped 10-digit RUT stays invalid", () => {
  expect(maskRutInput("1234567855")).toBe("123456785-5");
  expect(normalizeRut(maskRutInput("1234567855"))).toBeNull();
});

// Twenty RUT shapes a person can type or paste: what the field shows while typing, and what the API receives.
const RUT_CASES: { label: string; input: string; masked: string; normalized: string | null }[] = [
  { label: "8-digit body with dots and dash", input: "12.345.678-5", masked: "12345678-5", normalized: "12345678-5" },
  { label: "8-digit body without dots", input: "12345678-5", masked: "12345678-5", normalized: "12345678-5" },
  { label: "digits only, no dash", input: "123456785", masked: "12345678-5", normalized: "12345678-5" },
  { label: "7-digit body", input: "7123456-8", masked: "7123456-8", normalized: "7123456-8" },
  { label: "7-digit body with dots", input: "7.123.456-8", masked: "7123456-8", normalized: "7123456-8" },
  { label: "uppercase K check digit", input: "5500000-K", masked: "5500000-K", normalized: "5500000-K" },
  { label: "lowercase k check digit", input: "5500000k", masked: "5500000-K", normalized: "5500000-K" },
  { label: "8-digit body with k check digit", input: "11111112k", masked: "11111112-K", normalized: "11111112-K" },
  { label: "0 check digit", input: "12345675-0", masked: "12345675-0", normalized: "12345675-0" },
  { label: "company RUT ending in 0", input: "76.123.456-0", masked: "76123456-0", normalized: "76123456-0" },
  { label: "smallest 7-digit body", input: "1000000-9", masked: "1000000-9", normalized: "1000000-9" },
  { label: "largest 8-digit body", input: "99999999-9", masked: "99999999-9", normalized: "99999999-9" },
  { label: "spaces around and inside", input: " 20 123 456 5 ", masked: "20123456-5", normalized: "20123456-5" },
  { label: "letters other than k are dropped", input: "15a654b321c7", masked: "15654321-7", normalized: "15654321-7" },
  { label: "k typed in the middle is dropped", input: "1000k0009", masked: "1000000-9", normalized: null },
  { label: "wrong check digit", input: "12345678-6", masked: "12345678-6", normalized: null },
  { label: "k where the computed digit is a number", input: "7123456-k", masked: "7123456-K", normalized: null },
  { label: "6-digit body is too short", input: "123456-7", masked: "123456-7", normalized: null },
  { label: "extra digits beyond the 8-digit body are kept and stay invalid", input: "1234567855", masked: "123456785-5", normalized: null },
  { label: "empty input", input: "", masked: "", normalized: null },
];

for (const { label, input, masked, normalized } of RUT_CASES) {
  test(`RUT case: ${label}`, () => {
    expect(maskRutInput(input)).toBe(masked);
    expect(normalizeRut(input)).toBe(normalized);
    expect(normalizeRut(maskRutInput(input))).toBe(masked && isValidRut(masked) ? masked : null);
  });
}

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
