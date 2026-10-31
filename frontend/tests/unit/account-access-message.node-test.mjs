import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const { accountAccessMessage } = await import("../../src/lib/provider-request-access.ts");

test("sign-in on the panel asks for a confirmed email sign-in", () => {
  assert.equal(accountAccessMessage("sign-in", "panel"), "Inicia sesión con tu correo confirmado para ver tu panel.");
});

test("sign-in on the profile asks for a confirmed email sign-in", () => {
  assert.equal(accountAccessMessage("sign-in", "profile"), "Inicia sesión con tu correo confirmado para ver tu perfil.");
});

test("aal2 on the panel asks for SMS verification", () => {
  assert.equal(accountAccessMessage("aal2", "panel"), "Verifica tu teléfono por SMS para ver tu panel.");
});

test("aal2 on the profile asks for SMS verification", () => {
  assert.equal(accountAccessMessage("aal2", "profile"), "Verifica tu teléfono por SMS para ver tu perfil.");
});

test("session expiry gives the same message for both subjects", () => {
  assert.equal(accountAccessMessage("session", "panel"), "Tu sesión expiró. Inicia sesión nuevamente para continuar.");
  assert.equal(accountAccessMessage("session", "profile"), "Tu sesión expiró. Inicia sesión nuevamente para continuar.");
});
