import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const { TERMS_VERSION, TERMS_TITLE, TERMS_SECTIONS, splitStrong } = await import("../../src/lib/legal/terms.ts");

test("terms version is the fixed contract string shared with the backend", () => {
  assert.equal(TERMS_VERSION, "2026-11-23");
});

test("terms title matches the dialog heading the spec quotes", () => {
  assert.equal(TERMS_TITLE, "Términos y Condiciones de Uso de Amira");
});

test("terms content lists the fifteen sections of the legal document in order", () => {
  assert.deepEqual(
    TERMS_SECTIONS.map((section) => section.title),
    [
      "1. Quiénes somos y qué es Amira",
      "2. Definiciones",
      "3. De qué se encarga Amira",
      "4. De qué NO se encarga Amira",
      "5. Cuentas y verificación",
      "6. Obligaciones del Cliente",
      "7. Obligaciones del Transportista",
      "8. Precios, pago y comisión",
      "9. Cancelaciones",
      "10. Conformidad, reclamos y liberación del pago",
      "11. Rutas compartidas y servicio exclusivo",
      "12. Datos personales y privacidad",
      "13. Responsabilidad de Amira",
      "14. Cambios a estos Términos",
      "15. Ley aplicable y contacto",
    ],
  );
});

test("draft note from the legal document is dropped while placeholders stay", () => {
  const serialized = JSON.stringify(TERMS_SECTIONS);
  assert.equal(serialized.includes("Borrador para la demostración"), false);
  assert.equal(serialized.includes("[razón social]"), true);
  assert.equal(serialized.includes("[correo de contacto]"), true);
});

test("key sentences are transcribed verbatim", () => {
  const serialized = JSON.stringify(TERMS_SECTIONS);
  assert.equal(serialized.includes("**Amira es un intermediario, no una empresa de transporte.**"), true);
  assert.equal(serialized.includes("La comisión de Amira es $8.000 ($6.723 + $1.277 de IVA). El Transportista recibe $72.000."), true);
  assert.equal(serialized.includes("Se devuelve el **90 %**. Amira retiene el **10 %** por gastos de gestión"), true);
});

test("splitStrong separates bold segments from plain text", () => {
  assert.deepEqual(splitStrong("a **b** c"), [
    { text: "a ", strong: false },
    { text: "b", strong: true },
    { text: " c", strong: false },
  ]);
  assert.deepEqual(splitStrong("sin negrita"), [{ text: "sin negrita", strong: false }]);
});
