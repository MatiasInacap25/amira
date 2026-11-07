import { expect, test, type Page, type Route } from "@playwright/test";

const user = {
  id: "company-user-1",
  aud: "authenticated",
  role: "authenticated",
  email: "empresa@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const phoneFactor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

function accessToken(aal: "aal1" | "aal2", id = `${aal}-access-token`) {
  const payload = Buffer.from(JSON.stringify({ aal, exp: 2000000000, sub: user.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.${id}`;
}

function session(aal: "aal1" | "aal2" = "aal1", tokenId?: string, expiresIn = 3600) {
  return {
    access_token: accessToken(aal, tokenId),
    token_type: "bearer",
    expires_in: expiresIn,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    refresh_token: "refresh-test-token",
    user,
  };
}

// Auth calls for the email/password, SMS MFA and session checks, as the vehicle page spec does.
async function mockAuth(page: Page) {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const authPath = url.pathname.replace("/auth/v1", "");
    const method = request.method();

    if (authPath === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: session("aal1", "password-aal1-token") });
      return;
    }
    if (authPath === "/user" && method === "GET") {
      await route.fulfill({ json: { ...user, factors: [phoneFactor] } });
      return;
    }
    if (authPath === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: [phoneFactor], phone: [phoneFactor], totp: [] } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/challenge" && method === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/verify" && method === "POST") {
      await route.fulfill({ json: session("aal2", "verified-aal2-token") });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${authPath}` } });
  });
}

async function signInToTrips(page: Page) {
  await mockAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "company_owner", profile_id: "company-profile-1" } }));
  await page.goto("/login?next=%2Fcuenta%2Fviajes-compartidos");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/viajes-compartidos$/);
}

function trip(overrides: Record<string, unknown> = {}) {
  return {
    tripId: "trip-1",
    status: "open",
    origin: "Santiago",
    destination: "Valparaíso",
    departureAt: "2026-11-20T09:00:00-03:00",
    joinedServices: 2,
    ...overrides,
  };
}

// Serves the trip list and closes trips like the backend does. Every call is recorded.
async function mockTripsApi(page: Page, initial: ReturnType<typeof trip>[]) {
  const trips = initial.map((item) => ({ ...item }));
  const requests: Array<{ method: string; path: string }> = [];
  await page.route("**/api/provider/shared-trips**", async (route: Route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    const url = new URL(request.url());
    requests.push({ method: request.method(), path: url.pathname });
    if (request.method() === "GET") {
      await route.fulfill({ headers: corsHeaders, json: { items: trips, total: trips.length, limit: 20, offset: 0 } });
      return;
    }
    const closeMatch = url.pathname.match(/\/api\/provider\/shared-trips\/([^/]+)\/close$/);
    if (request.method() === "POST" && closeMatch) {
      const target = trips.find((item) => item.tripId === closeMatch[1]);
      if (target) target.status = "closed";
      await route.fulfill({ status: target ? 200 : 404, headers: corsHeaders, json: target ? { tripId: target.tripId, acceptsRequests: false } : { detail: "Not found" } });
      return;
    }
    await route.fulfill({ status: 405, headers: corsHeaders, json: { detail: "Method not allowed" } });
  });
  return { requests };
}

test.describe("cuenta viajes compartidos", () => {
  test("lists each trip with route, date, status and joined services, and closes an open trip to new requests", async ({ page }) => {
    const api = await mockTripsApi(page, [
      trip(),
      trip({ tripId: "trip-2", origin: "Concepción", destination: "Temuco", status: "closed", joinedServices: 1, departureAt: "2026-11-25T08:00:00-03:00" }),
    ]);
    await signInToTrips(page);

    await expect(page.getByRole("heading", { name: "Viajes compartidos", level: 1 })).toBeVisible();
    const list = page.getByRole("list", { name: "Viajes compartidos publicados" });
    const items = list.getByRole("listitem");
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText("Santiago a Valparaíso");
    await expect(items.nth(0)).toContainText("Abierto");
    await expect(items.nth(0)).toContainText("2 servicios");
    await expect(items.nth(1)).toContainText("Cerrado");
    // Only open trips offer the close action.
    await expect(items.nth(1).getByRole("button", { name: "Cerrar a nuevas solicitudes" })).toHaveCount(0);

    await items.nth(0).getByRole("button", { name: "Cerrar a nuevas solicitudes" }).click();

    await expect(items.nth(0)).toContainText("Cerrado");
    await expect(items.nth(0).getByRole("button", { name: "Cerrar a nuevas solicitudes" })).toHaveCount(0);
    const close = api.requests.find((entry) => entry.method === "POST");
    expect(close?.path).toBe("/api/provider/shared-trips/trip-1/close");
  });
});
