import { expect, test } from "@playwright/test";
import { accountApiFetch } from "../src/lib/auth/account-api";
import { createClient } from "../src/lib/supabase/client";

test("missing or invalid API configuration fails before sending an authenticated request", async () => {
  let requests = 0;
  const fetcher: typeof fetch = async () => {
    requests += 1;
    return new Response(null, { status: 200 });
  };

  await expect(accountApiFetch("/api/account/me", "sensitive-access-token", undefined, {}, fetcher))
    .rejects.toThrow("La API todavía no está configurada correctamente.");
  await expect(accountApiFetch("/api/account/provision", "sensitive-access-token", "ftp://api.example.test", {}, fetcher))
    .rejects.toThrow("La API todavía no está configurada correctamente.");
  expect(requests).toBe(0);
});

test("malformed Supabase configuration throws a visible configuration error", () => {
  expect(() => createClient({ url: "not-a-url", publishableKey: "test-only-key" }))
    .toThrow("Supabase URL must be an absolute HTTP(S) URL.");
});
