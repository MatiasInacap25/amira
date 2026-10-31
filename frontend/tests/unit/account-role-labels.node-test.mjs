import assert from "node:assert/strict";
import { test } from "node:test";
import { accountRoleLabel } from "../../src/lib/account-role-labels.ts";

test("labels every backend account role in Spanish", () => {
  assert.equal(accountRoleLabel("client"), "Cliente");
  assert.equal(accountRoleLabel("independent_driver"), "Conductor independiente");
  assert.equal(accountRoleLabel("company_owner"), "Dueño de empresa");
  assert.equal(accountRoleLabel("company_driver"), "Conductor de empresa");
});

test("falls back to a no-role label for missing or unknown roles", () => {
  assert.equal(accountRoleLabel(null), "Cuenta sin rol asignado");
  assert.equal(accountRoleLabel(undefined), "Cuenta sin rol asignado");
  assert.equal(accountRoleLabel(""), "Cuenta sin rol asignado");
  assert.equal(accountRoleLabel("admin"), "Cuenta sin rol asignado");
});
