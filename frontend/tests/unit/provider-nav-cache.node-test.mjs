import assert from "node:assert/strict";
import { test } from "node:test";
import {
  providerNavPendingKey,
  providerNavRoleKey,
  PROVIDER_NAV_ROOT_KEY,
  PROVIDER_NAV_USER_KEY,
  providerNavStaleKeys,
} from "../../src/lib/provider-nav-cache.ts";

test("scopes the role and pending keys by the signed-in user", () => {
  assert.notDeepEqual(providerNavRoleKey("user-a"), providerNavRoleKey("user-b"));
  assert.notDeepEqual(providerNavPendingKey("user-a"), providerNavPendingKey("user-b"));
});

test("keeps role and pending keys under the nav root so they can be removed together", () => {
  assert.deepEqual(providerNavRoleKey("user-a").slice(0, PROVIDER_NAV_ROOT_KEY.length), [...PROVIDER_NAV_ROOT_KEY]);
  assert.deepEqual(providerNavPendingKey("user-a").slice(0, PROVIDER_NAV_ROOT_KEY.length), [...PROVIDER_NAV_ROOT_KEY]);
});

test("stale keys cover every per-user nav query but never the session user key", () => {
  const stale = providerNavStaleKeys();
  assert.equal(stale.length, 2);
  for (const key of stale) {
    assert.deepEqual(key.slice(0, PROVIDER_NAV_ROOT_KEY.length), [...PROVIDER_NAV_ROOT_KEY]);
    assert.notDeepEqual(key, PROVIDER_NAV_USER_KEY);
  }
});
