import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const {
  PHONE_CHANGE_PATH,
  normalizePhone,
  phoneChangeError,
  phoneInputError,
  replacedPhoneFactorIds,
} = await import("../../src/lib/phone-change.ts");

test("the phone is normalized by dropping spaces, parentheses and dashes", () => {
  assert.equal(normalizePhone(" +56 (9) 2222-2222 "), "+56922222222");
});

test("a phone in international format is valid", () => {
  assert.equal(phoneInputError("+56 9 2222 2222", "+56911111111"), null);
});

test("an empty or local phone is flagged", () => {
  assert.equal(phoneInputError("  ", "+56911111111"), "Ingresa el número nuevo.");
  assert.equal(phoneInputError("922222222", "+56911111111"), "Ingresa un número internacional con código de país, por ejemplo +56912345678.");
});

test("the current phone cannot be the new one", () => {
  assert.equal(phoneInputError("+56 9 1111 1111", "+56911111111"), "Ese ya es tu número actual.");
});

test("only other verified phone factors are replaced", () => {
  const factors = [
    { id: "new", factor_type: "phone", status: "verified" },
    { id: "old", factor_type: "phone", status: "verified" },
    { id: "pending", factor_type: "phone", status: "unverified" },
    { id: "app", factor_type: "totp", status: "verified" },
  ];
  assert.deepEqual(replacedPhoneFactorIds(factors, "new"), ["old"]);
});

function response(status, body) {
  return new Response(body === undefined ? "" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("the API's Spanish detail is shown for 403 and 422 string answers", async () => {
  const detail = "Verifica el número nuevo con el código SMS antes de guardarlo.";
  assert.equal(await phoneChangeError(response(403, { detail })), detail);
  assert.equal(await phoneChangeError(response(422, { detail })), detail);
});

test("other failures get fixed Spanish messages", async () => {
  assert.equal(await phoneChangeError(response(422, { detail: [{ msg: "x" }] })), "Ingresa un número internacional con código de país, por ejemplo +56912345678.");
  assert.equal(await phoneChangeError(response(503, { detail: "boom" })), "No pudimos comprobar el número. Inténtalo más tarde.");
  assert.equal(await phoneChangeError(response(500)), "No pudimos guardar el número. Inténtalo nuevamente.");
});

test("the phone change endpoint is the account phone path", () => {
  assert.equal(PHONE_CHANGE_PATH, "/api/account/phone");
});
