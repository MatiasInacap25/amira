import { expect, test, type Page, type Route } from "@playwright/test";
import { locationsResponse } from "./support/catalog-fixtures";

const user = {
  id: "user-test-1",
  aud: "authenticated",
  role: "authenticated",
  email: "persona@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const phoneFactor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };

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

function providerRequest(overrides: Record<string, unknown> = {}) {
  return {
    requestId: "request-provider-1",
    status: "pending",
    origin: "Calle Uno 123",
    destination: "Av. Dos 456",
    originCommuneCode: "13101",
    originCommuneName: "Santiago",
    originRegionName: "Metropolitana de Santiago",
    destinationCommuneCode: "05101",
    destinationCommuneName: "Valparaíso",
    destinationRegionName: "Valparaíso",
    isExclusive: false,
    customerFirstName: "Camila",
    customerLastName: null,
    requestedAt: "2026-10-12T12:00:00Z",
    createdAt: "2026-10-01T12:00:00Z",
    estimatedWeight: "250.5",
    estimatedVolume: null,
    description: "Retiro de muebles.",
    cargoMeasurements: "2 x 1 x 1 m",
    serviceName: "Mudanzas",
    chatId: null,
    ...overrides,
  };
}

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in auth.spec.ts.
async function mockSmsVerifiedProviderAuth(page: Page) {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();

    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: session("aal1", "password-aal1-token") });
      return;
    }
    if (path === "/user" && method === "GET") {
      await route.fulfill({ json: { ...user, factors: [phoneFactor] } });
      return;
    }
    if (path === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: [phoneFactor], phone: [phoneFactor], totp: [] } });
      return;
    }
    if (path === "/factors/factor-sms-1/challenge" && method === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 } });
      return;
    }
    if (path === "/factors/factor-sms-1/verify" && method === "POST") {
      await route.fulfill({ json: session("aal2", "verified-aal2-token") });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await page.route("**/api/locations", async (route) => route.fulfill({ json: locationsResponse }));
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role: "client", profile_id: null } }));
}

async function signInAsSmsVerifiedProvider(page: Page) {
  await mockSmsVerifiedProviderAuth(page);
  await page.goto("/login?next=%2Fsolicitudes");
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/solicitudes$/);
}

type InboxResponder = (url: URL, route: Route) => Promise<void>;

// Answers GET /api/provider/requests with the handler and records every query string it receives.
async function mockProviderRequests(page: Page, respond: InboxResponder) {
  const queries: URLSearchParams[] = [];
  await page.route("**/api/provider/requests**", async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    await respond(url, route);
  });
  return queries;
}

function pageOf(items: unknown[], total = items.length, offset = 0, counts = { pending: 0, accepted: 0, rejected: 0 }) {
  return { items, total, limit: 20, offset, counts };
}

test("signed-out visitor is asked to sign in and no inbox data is requested", async ({ page }) => {
  const queries = await mockProviderRequests(page, async (_url, route) => route.fulfill({ json: pageOf([]) }));

  await page.goto("/solicitudes");

  const alert = page.locator(".provider-inbox-panel [role=alert]");
  await expect(alert).toHaveText("Inicia sesión con tu correo confirmado para ver las solicitudes.");
  await expect(page.getByRole("tabpanel").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fsolicitudes");
  expect(queries).toHaveLength(0);
});

test("status tabs show their counts and each tab has its own empty state", async ({ page }) => {
  await mockProviderRequests(page, async (url, route) => {
    const status = url.searchParams.get("status");
    const items = status === "pending" ? [providerRequest(), providerRequest({ requestId: "request-provider-2" })] : [];
    await route.fulfill({ json: pageOf(items, items.length, 0, { pending: 2, accepted: 0, rejected: 3 }) });
  });
  await signInAsSmsVerifiedProvider(page);

  await expect(page.getByRole("tab", { name: /Pendientes/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: /Pendientes/ })).toContainText("2");
  await expect(page.getByRole("tab", { name: /Rechazadas/ })).toContainText("3");
  await expect(page.locator(".provider-request-list li")).toHaveCount(2);

  await page.getByRole("tab", { name: /Aceptadas/ }).click();
  await expect(page.getByRole("tab", { name: /Aceptadas/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Todavía no has aceptado solicitudes." })).toBeVisible();
  await expect(page.locator(".provider-request-list")).toHaveCount(0);

  await page.getByRole("tab", { name: /Rechazadas/ }).click();
  await expect(page.getByRole("heading", { name: "No tienes solicitudes rechazadas." })).toBeVisible();
});

test("arrow keys and Home/End move between status tabs and select the focused tab", async ({ page }) => {
  await mockProviderRequests(page, async (_url, route) => route.fulfill({ json: pageOf([]) }));
  await signInAsSmsVerifiedProvider(page);

  const pendingTab = page.getByRole("tab", { name: /Pendientes/ });
  await pendingTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: /Aceptadas/ })).toBeFocused();
  await expect(page.getByRole("tab", { name: /Aceptadas/ })).toHaveAttribute("aria-selected", "true");

  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: /Rechazadas/ })).toBeFocused();
  await expect(page.getByRole("tab", { name: /Rechazadas/ })).toHaveAttribute("aria-selected", "true");

  await page.keyboard.press("ArrowRight");
  await expect(pendingTab).toBeFocused();
  await expect(pendingTab).toHaveAttribute("aria-selected", "true");

  await page.keyboard.press("Home");
  await expect(pendingTab).toBeFocused();
});

test("load more requests the next offset and appends the following rows", async ({ page }) => {
  const firstPage = Array.from({ length: 20 }, (_, index) => providerRequest({ requestId: `request-${index + 1}` }));
  const secondPage = [providerRequest({ requestId: "request-21" })];
  const queries = await mockProviderRequests(page, async (url, route) => {
    const offset = Number(url.searchParams.get("offset"));
    if (offset === 0) await route.fulfill({ json: pageOf(firstPage, 21, 0, { pending: 21, accepted: 0, rejected: 0 }) });
    else await route.fulfill({ json: pageOf(secondPage, 21, 20, { pending: 21, accepted: 0, rejected: 0 }) });
  });
  await signInAsSmsVerifiedProvider(page);

  await expect(page.locator(".provider-request-list li")).toHaveCount(20);
  await page.getByRole("button", { name: "Cargar más" }).click();
  await expect(page.locator(".provider-request-list li")).toHaveCount(21);
  await expect(page.getByRole("button", { name: "Cargar más" })).toHaveCount(0);

  expect(queries.some((params) => params.get("offset") === "20" && params.get("status") === "pending")).toBe(true);
});

test("request rows show route, customer first name, and a link to the request detail", async ({ page }) => {
  await mockProviderRequests(page, async (_url, route) => route.fulfill({ json: pageOf([providerRequest()], 1, 0, { pending: 1, accepted: 0, rejected: 0 }) }));
  await signInAsSmsVerifiedProvider(page);

  const row = page.locator(".provider-request-card");
  await expect(row.getByText("Mudanzas", { exact: true })).toBeVisible();
  await expect(row.getByText("Cliente: Camila", { exact: true })).toBeVisible();
  await expect(row.getByRole("link", { name: /Santiago, Metropolitana de Santiago\s+Valparaíso, Valparaíso/ })).toHaveAttribute(
    "href",
    "/solicitudes/request-provider-1",
  );
  await expect(row.getByText("Pendiente", { exact: true })).toBeVisible();
});

test("accepted rows show the full customer name and the location fallback when no commune is set", async ({ page }) => {
  const accepted = providerRequest({
    status: "accepted",
    customerLastName: "Rojas",
    originCommuneName: null,
    originRegionName: null,
    origin: "Calle Uno 123",
    chatId: "chat-provider-1",
  });
  await mockProviderRequests(page, async (url, route) => {
    const status = url.searchParams.get("status");
    await route.fulfill({ json: pageOf(status === "accepted" ? [accepted] : [], status === "accepted" ? 1 : 0, 0, { pending: 0, accepted: 1, rejected: 0 }) });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("tab", { name: /Aceptadas/ }).click();
  const row = page.locator(".provider-request-card");
  await expect(row.getByText("Cliente: Camila Rojas", { exact: true })).toBeVisible();
  await expect(row.getByText("Aceptada", { exact: true })).toBeVisible();
  await expect(row.getByRole("link", { name: /Calle Uno 123\s+Valparaíso, Valparaíso/ })).toBeVisible();
});

test("a failed list request shows a retryable error that recovers the inbox", async ({ page }) => {
  let attempts = 0;
  await mockProviderRequests(page, async (_url, route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 500, json: { detail: "Internal error" } });
    else await route.fulfill({ json: pageOf([providerRequest()], 1, 0, { pending: 1, accepted: 0, rejected: 0 }) });
  });
  await signInAsSmsVerifiedProvider(page);

  const panel = page.locator(".provider-inbox-panel");
  await expect(panel.locator("[role=alert]")).toContainText("No pudimos cargar las solicitudes. Inténtalo nuevamente.");
  await expect(panel.getByRole("button", { name: "Reintentar" })).toBeVisible();
  await expect(page.locator(".provider-request-list")).toHaveCount(0);

  await panel.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.locator(".provider-request-list li")).toHaveCount(1);
  await expect(panel.locator("[role=alert]")).toHaveCount(0);
});

test("inbox fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockProviderRequests(page, async (_url, route) => route.fulfill({ json: pageOf([providerRequest()], 1, 0, { pending: 1, accepted: 0, rejected: 0 }) }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.locator(".provider-request-list li")).toHaveCount(1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
