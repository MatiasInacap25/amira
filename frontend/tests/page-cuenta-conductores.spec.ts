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

async function signInToDrivers(page: Page) {
  await mockAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "company_owner", profile_id: "company-profile-1" } }));
  await page.goto("/login?next=%2Fcuenta%2Fconductores");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/conductores$/);
}

type Driver = { driverId: string; firstName: string; lastName: string; email: string; phone: string | null; verified: boolean; isOwner: boolean };

function driver(overrides: Partial<Driver> = {}): Driver {
  return { driverId: "driver-1", firstName: "Eli", lastName: "Rojas", email: "eli@example.test", phone: "+56912345678", verified: true, isOwner: false, ...overrides };
}

async function mockDriversApi(page: Page, response: { status?: number; items?: Driver[] }) {
  await page.route("**/api/company/profiles/me/drivers", async (route: Route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (response.status && response.status !== 200) {
      await route.fulfill({ status: response.status, headers: corsHeaders, json: { detail: "error" } });
      return;
    }
    await route.fulfill({ headers: corsHeaders, json: { items: response.items ?? [] } });
  });
}

test.describe("cuenta conductores", () => {
  test("lists linked drivers with contact data and verification state", async ({ page }) => {
    await mockDriversApi(page, { items: [
      driver(),
      driver({ driverId: "driver-2", firstName: "Pat", lastName: "Soto", email: "pat@example.test", phone: null, verified: false, isOwner: true }),
    ] });
    await signInToDrivers(page);

    await expect(page.getByRole("heading", { name: "Conductores", level: 1 })).toBeVisible();
    const items = page.getByRole("list", { name: "Conductores enlazados" }).getByRole("listitem");
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText("Eli Rojas");
    await expect(items.nth(0)).toContainText("eli@example.test");
    await expect(items.nth(0)).toContainText("+56912345678");
    await expect(items.nth(0)).toContainText("Verificado");
    await expect(items.nth(1)).toContainText("Pat Soto");
    await expect(items.nth(1)).toContainText("Dueño");
    await expect(items.nth(1)).toContainText("No indicado");
    await expect(items.nth(1)).toContainText("Sin verificar");
  });

  test("shows an empty state that links to invitations", async ({ page }) => {
    await mockDriversApi(page, { items: [] });
    await signInToDrivers(page);

    await expect(page.getByText("Todavía no tienes conductores enlazados.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Invitar conductores" })).toHaveAttribute("href", "/cuenta/invitaciones");
  });

  test("tells non-owners the page is not available", async ({ page }) => {
    await mockDriversApi(page, { status: 403 });
    await signInToDrivers(page);

    await expect(page.locator(".auth-form-wrap").getByRole("alert")).toHaveText("Esta sección solo está disponible para dueños de empresa.");
  });

  test("shows a retryable error when the list fails", async ({ page }) => {
    await mockDriversApi(page, { status: 500 });
    await signInToDrivers(page);

    await expect(page.locator(".auth-form-wrap").getByRole("alert")).toHaveText("No pudimos cargar los conductores.");
    await expect(page.getByRole("button", { name: "Reintentar" })).toBeVisible();
  });
});
