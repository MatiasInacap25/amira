import assert from "node:assert/strict";
import { test } from "node:test";
import { acceptsAssuranceLevel, isDevelopmentAppEnv, isDevSkipSmsMfaEnabled } from "../../src/lib/auth/dev-mfa.ts";

test("the dev app environment allowlist admits development, local and test, ignoring case and spaces", () => {
  assert.equal(isDevelopmentAppEnv("development"), true);
  assert.equal(isDevelopmentAppEnv("local"), true);
  assert.equal(isDevelopmentAppEnv("test"), true);
  assert.equal(isDevelopmentAppEnv(" Development "), true);
  assert.equal(isDevelopmentAppEnv("LOCAL"), true);
});

test("the dev app environment allowlist fails closed for unset, empty, production and unknown values", () => {
  assert.equal(isDevelopmentAppEnv(undefined), false);
  assert.equal(isDevelopmentAppEnv(""), false);
  assert.equal(isDevelopmentAppEnv("production"), false);
  assert.equal(isDevelopmentAppEnv("preview"), false);
  assert.equal(isDevelopmentAppEnv("developmnet"), false);
});

test("enables the SMS skip when the flag is 'true' and the app environment is development, local or test", () => {
  assert.equal(isDevSkipSmsMfaEnabled("true", "development"), true);
  assert.equal(isDevSkipSmsMfaEnabled("true", "local"), true);
  assert.equal(isDevSkipSmsMfaEnabled("true", "test"), true);
});

test("trims and ignores case when reading the app environment", () => {
  assert.equal(isDevSkipSmsMfaEnabled("true", " Development "), true);
  assert.equal(isDevSkipSmsMfaEnabled("true", "LOCAL"), true);
});

test("fails closed when the app environment is unset, empty, or not an allowlisted value", () => {
  assert.equal(isDevSkipSmsMfaEnabled("true", undefined), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", ""), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", "production"), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", "prod"), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", "staging"), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", "preview"), false);
  assert.equal(isDevSkipSmsMfaEnabled("true", "developmnet"), false);
});

test("keeps SMS MFA when the flag is missing, false or not exactly 'true'", () => {
  assert.equal(isDevSkipSmsMfaEnabled(undefined, "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("false", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled("TRUE", "development"), false);
  assert.equal(isDevSkipSmsMfaEnabled(" true", "development"), false);
});

test("uses the app environment rather than NODE_ENV, so a production build can run the bypass in development", () => {
  // Vercel builds with NODE_ENV=production; the explicit app environment is what decides.
  assert.equal(isDevSkipSmsMfaEnabled("true", "development"), true);
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
