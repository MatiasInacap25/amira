import assert from "node:assert/strict";
import { test } from "node:test";
import { documentConceptLabel, documentTypeLabel, IVA_RATE_PERCENT, splitIva } from "../../src/lib/tax.ts";

test("document type and concept labels match the spec wording", () => {
  assert.equal(documentTypeLabel("boleta"), "Boleta");
  assert.equal(documentTypeLabel("factura_comision"), "Factura de comisión");
  assert.equal(documentConceptLabel("boleta"), "Servicio de transporte");
  assert.equal(documentConceptLabel("factura_comision"), "Comisión por intermediación");
});

test("IVA rate is 19 percent", () => {
  assert.equal(IVA_RATE_PERCENT, 19);
});

test("splitIva extracts IVA from a total that already includes it (S0 example)", () => {
  assert.deepEqual(splitIva(80000), { net: 67227, iva: 12773 });
});

test("splitIva rounds the net half up, so the IVA absorbs the remainder", () => {
  // 80.000 / 1.19 = 67.226,89: a floor would give 67.226.
  assert.deepEqual(splitIva(80000), { net: 67227, iva: 12773 });
});

test("splitIva handles zero, one and the exact 119 boundary", () => {
  assert.deepEqual(splitIva(0), { net: 0, iva: 0 });
  assert.deepEqual(splitIva(1), { net: 1, iva: 0 });
  assert.deepEqual(splitIva(119), { net: 100, iva: 19 });
});

test("splitIva keeps net + iva equal to the total for larger amounts", () => {
  assert.deepEqual(splitIva(10001), { net: 8404, iva: 1597 });
  const { net, iva } = splitIva(125000);
  assert.equal(net + iva, 125000);
  assert.deepEqual(splitIva(125000), { net: 105042, iva: 19958 });
});

test("splitIva rejects values that are not whole non-negative pesos", () => {
  assert.throws(() => splitIva(-1), RangeError);
  assert.throws(() => splitIva(10.5), RangeError);
  assert.throws(() => splitIva(Number.NaN), RangeError);
});
