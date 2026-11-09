import assert from "node:assert/strict";
import { register } from "node:module";
import { afterEach, test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
register("./whitebox-client-loader.mjs", import.meta.url);
const access = await import("../../src/lib/provider-request-access.ts");
const profiles = await import("../../src/lib/provider-profile-api.ts");
const account = await import("../../src/lib/auth/account-api.ts");

const originalFetch = globalThis.fetch;
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL;
afterEach(() => {
  globalThis.fetch = originalFetch;
  delete globalThis.__whiteboxSupabase;
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = originalApiUrl;
});

function client({ userError = null, confirmed = true, assuranceError = null, level = "aal2", sessionError = null, token = "token" } = {}) {
  return {
    auth: {
      getUser: async () => ({ data: { user: confirmed ? { email_confirmed_at: "confirmed" } : null }, error: userError }),
      mfa: { getAuthenticatorAssuranceLevel: async () => ({ data: { currentLevel: level }, error: assuranceError }) },
      getSession: async () => ({ data: { session: token === null ? null : { access_token: token } }, error: sessionError }),
    },
  };
}

for (const [name, options, reason] of [
  ["user-error", { userError: new Error("offline") }, "sign-in"],
  ["unconfirmed", { confirmed: false }, "sign-in"],
  ["missing-assurance", { level: "aal1" }, "aal2"],
  ["session-error", { sessionError: new Error("offline") }, "session"],
  ["missing-session", { token: null }, "session"],
  ["empty-token", { token: "" }, "session"],
]) {
  test(`currentAccessToken rejects ${name} with its typed reason`, async () => {
    globalThis.__whiteboxSupabase = client(options);
    await assert.rejects(access.currentAccessToken(), (error) => error instanceof access.ProviderRequestAccessError && error.reason === reason);
  });
}

test("currentAccessToken returns only the confirmed AAL2 session token", async () => {
  globalThis.__whiteboxSupabase = client();
  assert.equal(await access.currentAccessToken(), "token");
});

test("currentAccessToken propagates assurance provider errors", async () => {
  const failure = new Error("assurance unavailable");
  globalThis.__whiteboxSupabase = client({ assuranceError: failure });
  await assert.rejects(access.currentAccessToken(), (error) => error === failure);
});

test("access errors map to stable public messages", () => {
  for (const reason of ["sign-in", "aal2", "session"]) {
    const error = new access.ProviderRequestAccessError(reason);
    assert.equal(access.isSignInRequired(error), true);
    assert.match(access.paymentAccessMessage(reason), /sesión|teléfono/);
    assert.match(access.requestErrorMessage(error), /sesión|teléfono/);
  }
  assert.equal(access.isSignInRequired(new Error("network")), false);
  assert.equal(access.requestErrorMessage(new Error("API todavía no está configurada")), "API todavía no está configurada");
  assert.equal(access.requestErrorMessage(null), "No pudimos cargar las solicitudes. Inténtalo nuevamente.");
});

for (const value of [undefined, " ", "not a URL", "ftp://api.test", "https://user:pass@api.test", "https://api.test?x=1", "https://api.test/#fragment"]) {
  test(`API base rejects unsafe configuration ${String(value)}`, () => {
    assert.throws(() => account.resolveApiBaseUrl(value), account.ApiConfigurationError);
  });
}

test("API base normalizes whitespace and trailing slash", () => {
  assert.equal(account.resolveApiBaseUrl(" https://api.test/base/ "), "https://api.test/base");
  assert.equal(account.resolveApiBaseUrl("http://localhost:8000"), "http://localhost:8000");
});

test("accountApiFetch preserves request options but owns Authorization and cache", async () => {
  const calls = [];
  const response = new Response("{}", { status: 201 });
  const fetcher = async (...args) => { calls.push(args); return response; };
  const options = { method: "POST", body: "{}", headers: { Accept: "application/json", Authorization: "forged" }, cache: "force-cache" };
  assert.equal(await account.accountApiFetch("/api/account/provision", "trusted", "https://api.test", options, fetcher), response);
  assert.equal(calls[0][0], "https://api.test/api/account/provision");
  assert.deepEqual(calls[0][1], { ...options, headers: { Accept: "application/json", Authorization: "Bearer trusted" }, cache: "no-store" });
  globalThis.fetch = fetcher;
  await account.accountApiFetch("/api/account/me", "trusted", "https://api.test");
  await account.authenticatedApiFetch("/api/account/me", "trusted", "https://api.test");
  assert.equal(calls.length, 3);
});

test("invalid API configuration refuses before calling fetch", async () => {
  let calls = 0;
  await assert.rejects(account.accountApiFetch("/api/account/me", "secret", undefined, {}, async () => { calls++; }), account.ApiConfigurationError);
  assert.equal(calls, 0);
});

const input = { description: "Description", commune_code: "13101", service_type_ids: [] };
for (const [name, operation, method, suffix] of [
  ["read", (signal) => profiles.requestProviderProfile("token", signal), undefined, ""],
  ["save", () => profiles.saveProviderProfile("token", input), "PUT", ""],
  ["publish", () => profiles.publishProviderProfile("token"), "POST", "/publish"],
  ["unpublish", () => profiles.unpublishProviderProfile("token"), "POST", "/unpublish"],
]) {
  test(`profile ${name} sends the authenticated request and parses its response`, async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.test";
    const signal = new AbortController().signal;
    const body = { profileId: "profile", published: false };
    let calls = 0;
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.equal(url, `https://api.test/api/provider/profile${suffix}`);
      assert.equal(options.method, method);
      assert.equal(options.headers.Authorization, "Bearer token");
      assert.equal(options.cache, "no-store");
      if (name === "read") assert.equal(options.signal, signal);
      if (name === "save") {
        assert.deepEqual(JSON.parse(options.body), input);
        assert.equal(options.headers["Content-Type"], "application/json");
      }
      return Response.json(body);
    };
    assert.deepEqual(await operation(signal), body);
    assert.equal(calls, 1);
  });
}

for (const [status, body] of [[401, { detail: "unauthorized" }], [422, { detail: { missing: ["commune"] } }], [503, null]]) {
  test(`profile errors retain status ${status} and parsed or invalid body`, async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.test";
    globalThis.fetch = async () => body === null ? new Response("invalid JSON", { status }) : Response.json(body, { status });
    await assert.rejects(profiles.requestProviderProfile("token"), (error) => error instanceof profiles.ProviderProfileError && error.status === status && JSON.stringify(error.body) === JSON.stringify(body));
  });
}

test.todo("BUG: authenticatedApiFetch drops Headers values from RequestInit", async () => {
  let sent;
  await account.authenticatedApiFetch("/api/account/me", "token", "https://api.test", { headers: new Headers({ Accept: "application/json" }) }, async (_url, options) => { sent = new Headers(options.headers); return new Response(); });
  assert.equal(sent.get("Accept"), "application/json");
  assert.equal(sent.get("Authorization"), "Bearer token");
});
