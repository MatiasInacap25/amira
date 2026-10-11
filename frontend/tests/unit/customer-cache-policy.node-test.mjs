import assert from "node:assert/strict";
import { test } from "node:test";
import { shouldClearCustomerCache } from "../../src/lib/customer-cache-policy.ts";

test("clears the customer cache on sign-out", () => {
  assert.equal(shouldClearCustomerCache("SIGNED_OUT", "user-a", undefined), true);
  assert.equal(shouldClearCustomerCache("SIGNED_OUT", undefined, undefined), true);
});

test("keeps the cache when the same account signs in or refreshes its token", () => {
  assert.equal(shouldClearCustomerCache("SIGNED_IN", "user-a", "user-a"), false);
  assert.equal(shouldClearCustomerCache("TOKEN_REFRESHED", "user-a", "user-a"), false);
  assert.equal(shouldClearCustomerCache("USER_UPDATED", "user-a", "user-a"), false);
});

test("clears the cache when a different account becomes the session user", () => {
  assert.equal(shouldClearCustomerCache("SIGNED_IN", "user-a", "user-b"), true);
  assert.equal(shouldClearCustomerCache("TOKEN_REFRESHED", "user-a", "user-b"), true);
});

test("does nothing when no account was cached yet", () => {
  assert.equal(shouldClearCustomerCache("SIGNED_IN", undefined, "user-b"), false);
  assert.equal(shouldClearCustomerCache("TOKEN_REFRESHED", undefined, "user-a"), false);
});
