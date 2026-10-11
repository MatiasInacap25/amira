import assert from "node:assert/strict";
import { test } from "node:test";
import { acceptsAssuranceLevel, isDevSkipSmsMfaEnabled } from "../../src/lib/auth/dev-mfa.ts";

test("enables the SMS skip only when the flag is exactly 'true' outside production", () => {
  assert.equal(isDevSkipSmsMfaEnabled("true", "development"), true);
  assert.equal(isDevSkipSmsMfaEnabled("true", "test"), true);
  assert.equal(isDevSkipSmsMfaEnabled("true", undefined), true);
});

test("keeps SMS MFA when the flag is missing, false or not exactly 'true'", () => {
  assert.equal(isDevSkipSmsMfaEnabled(undefined, "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("false", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("TRUE", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled(" true", "development"), false);
});

test("never enables the SMS skip in production, even with the flag set", () => {
  assert.equal(isDevSkipSmsMfaEnabled("true", "production"), false);
});

test("accepts aal2 sessions regardless of the development switch", () => {
  assert.equal(acceptsAssuranceLevel("aal2", false), true);
  assert.equal(acceptsAssuranceLevel("aal2", true), true);
});

test("accepts an aal1 password session only while the development switch is active", () => {
  assert.equal(acceptsAssuranceLevel("aal1", true), true);
  assert.equal(acceptsAssuranceLevel("aal1", false), false);
});

test("rejects missing or unknown assurance levels even with the switch active", () => {
  assert.equal(acceptsAssuranceLevel(null, true), false);
  assert.equal(acceptsAssuranceLevel(undefined, true), false);
  assert.equal(acceptsAssuranceLevel("", true), false);
});
