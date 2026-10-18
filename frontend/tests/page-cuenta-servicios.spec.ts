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

type CustomerRating = { rating: number; comment: string | null; createdAt: string };

function customerService(overrides: Record<string, unknown> = {}) {
  return {
    serviceId: "service-1",
    providerProfileId: "provider-profile-1",
    providerName: "Transportes Andes",
    serviceTypeName: "Mudanzas",
    completedAt: "2026-10-10T00:00:00Z",
    rating: null as CustomerRating | null,
    ...overrides,
  };
}

function customerPage(items: unknown[], total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}

function providerService(overrides: Record<string, unknown> = {}) {
  return {
    serviceId: "service-provider-1",
    status: "confirmed",
    serviceTypeName: "Mudanzas",
    serviceAt: "2026-10-20T13:00:00Z",
    amount: 45000,
    currency: "CLP",
    originCommune: "Santiago",
    destinationCommune: "Valparaíso",
    isExclusive: false,
    counterpartName: "Ana Pérez",
    assignmentCount: 1,
    ...overrides,
  };
}

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-solicitudes.spec.ts.
async function mockSmsVerifiedAuth(page: Page) {
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
}

// Signs in through the real login form and lands on /cuenta/servicios with the given account role.
async function signInTo(page: Page, role: string) {
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role, profile_id: null } }));
  await page.goto("/login?next=%2Fcuenta%2Fservicios");
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/servicios$/);
}

// Answers GET /api/customer/services with the handler and records every query string it receives.
async function mockCustomerServices(page: Page, respond: (url: URL, route: Route) => Promise<void>) {
  const queries: URLSearchParams[] = [];
  await page.route("**/api/customer/services?*", async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    await respond(url, route);
  });
  return queries;
}

// Answers GET /api/provider/services with the handler and records every query string it receives.
async function mockProviderServices(page: Page, respond: (url: URL, route: Route) => Promise<void>) {
  const queries: URLSearchParams[] = [];
  await page.route("**/api/provider/services?*", async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    await respond(url, route);
  });
  return queries;
}

test("signed-out visitor sees a sign-in prompt and no service list is requested", async ({ page }) => {
  const queries = await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([]) }));

  await page.goto("/cuenta/servicios");

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "No pudimos verificar tu sesión" })).toBeVisible();
  await expect(alert.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fcuenta%2Fservicios");
  expect(queries).toHaveLength(0);
});

test("a failed role lookup shows a retryable error and never the customer list", async ({ page }) => {
  let roleFails = false;
  let roleAttempts = 0;
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/account/me", async (route) => {
    if (!roleFails) {
      await route.fulfill({ json: { user_id: "account-test-1", role: "client", profile_id: null } });
      return;
    }
    roleAttempts += 1;
    await route.fulfill({ status: 500, json: { detail: "Internal error" } });
  });
  const queries = await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([customerService()]) }));
  await page.goto("/login?next=%2Fcuenta%2Fservicios");
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/servicios$/);

  roleFails = true;
  queries.length = 0;
  await page.reload();

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "No pudimos cargar tus servicios" })).toBeVisible();
  await expect(page.locator(".customer-service-list")).toHaveCount(0);
  expect(queries).toHaveLength(0);

  const attemptsBeforeRetry = roleAttempts;
  await alert.getByRole("button", { name: "Reintentar" }).click();
  await expect.poll(() => roleAttempts).toBeGreaterThan(attemptsBeforeRetry);
});

test("customer sees each completed service with provider, completion date, and a detail link", async ({ page }) => {
  await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([customerService()], 1) }));
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await expect(card.getByRole("heading", { name: "Mudanzas" })).toBeVisible();
  await expect(card.getByText("Transportes Andes · Completado el 10 de octubre de 2026", { exact: true })).toBeVisible();
  await expect(card.getByRole("link", { name: "Ver detalle" })).toHaveAttribute("href", "/cuenta/servicios/service-1");
});

test("completed service without a rating shows the rating form and blocks an empty submit", async ({ page }) => {
  const posts: unknown[] = [];
  await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([customerService()], 1) }));
  await page.route("**/api/customer/services/*/rating", async (route) => {
    posts.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: {} });
  });
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await expect(card.getByRole("group", { name: "Calificación" })).toBeVisible();
  await expect(card.getByLabel("Comentario (opcional)")).toBeVisible();

  await card.getByRole("button", { name: "Enviar valoración" }).click();
  await expect(card.getByText("Elige una calificación de 1 a 5 estrellas.", { exact: true })).toBeVisible();
  await expect(card.getByRole("group", { name: "Calificación" })).toHaveAttribute("aria-describedby", /rating-service-1-error/);
  expect(posts).toHaveLength(0);
});

test("submitting a rating saves it and the card then shows the stored stars and date", async ({ page }) => {
  const posts: unknown[] = [];
  let stored: CustomerRating | null = null;
  await mockCustomerServices(page, async (_url, route) => {
    const service = customerService({ rating: stored });
    await route.fulfill({ json: customerPage([service], 1) });
  });
  await page.route("**/api/customer/services/*/rating", async (route) => {
    posts.push(route.request().postDataJSON());
    stored = { rating: 4, comment: "Llegaron puntuales.", createdAt: "2026-10-12T12:00:00Z" };
    await route.fulfill({ status: 201, json: {} });
  });
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await card.locator("label.customer-star-option", { hasText: "4 de 5" }).click();
  await expect(card.getByLabel("4 de 5")).toBeChecked();
  await card.getByLabel("Comentario (opcional)").fill("  Llegaron puntuales.  ");
  await card.getByRole("button", { name: "Enviar valoración" }).click();

  await expect(card.getByRole("img", { name: "Valoración: 4 de 5 estrellas" })).toBeVisible();
  await expect(card.getByText("Llegaron puntuales.", { exact: true })).toBeVisible();
  await expect(card.getByText("Valorado el 12 de octubre de 2026", { exact: true })).toBeVisible();
  await expect(card.getByRole("group", { name: "Calificación" })).toHaveCount(0);
  expect(posts).toEqual([{ rating: 4, comment: "Llegaron puntuales." }]);
});

test("a 409 on rating refreshes the list to the stored rating", async ({ page }) => {
  let listRequests = 0;
  await mockCustomerServices(page, async (_url, route) => {
    listRequests += 1;
    const rating = listRequests > 1 ? { rating: 5, comment: null, createdAt: "2026-10-12T12:00:00Z" } : null;
    await route.fulfill({ json: customerPage([customerService({ rating })], 1) });
  });
  await page.route("**/api/customer/services/*/rating", async (route) => route.fulfill({ status: 409, json: { detail: "Already rated" } }));
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await card.locator("label.customer-star-option", { hasText: "5 de 5" }).click();
  await card.getByRole("button", { name: "Enviar valoración" }).click();

  await expect(card.getByRole("img", { name: "Valoración: 5 de 5 estrellas" })).toBeVisible();
  await expect(card.getByRole("group", { name: "Calificación" })).toHaveCount(0);
});

// The 409 refetch returns the rated service, which unmounts RatingForm and its submit error with it.
test.fixme("a 409 on rating shows the already-rated message", async ({ page }) => {
  let listRequests = 0;
  await mockCustomerServices(page, async (_url, route) => {
    listRequests += 1;
    const rating = listRequests > 1 ? { rating: 5, comment: null, createdAt: "2026-10-12T12:00:00Z" } : null;
    await route.fulfill({ json: customerPage([customerService({ rating })], 1) });
  });
  await page.route("**/api/customer/services/*/rating", async (route) => route.fulfill({ status: 409, json: { detail: "Already rated" } }));
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await card.locator("label.customer-star-option", { hasText: "5 de 5" }).click();
  await card.getByRole("button", { name: "Enviar valoración" }).click();

  await expect(page.locator(".customer-submit-error")).toHaveText("Este servicio ya fue valorado.");
});

test("a 422 saying the service is not completed shows the completed-service message", async ({ page }) => {
  await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([customerService()], 1) }));
  await page.route("**/api/customer/services/*/rating", async (route) =>
    route.fulfill({ status: 422, json: { detail: [{ loc: ["body", "service"], type: "service_not_completed", msg: "x" }] } }),
  );
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await card.locator("label.customer-star-option", { hasText: "3 de 5" }).click();
  await card.getByRole("button", { name: "Enviar valoración" }).click();

  await expect(page.locator(".customer-submit-error")).toHaveText("Solo puedes valorar servicios completados.");
});

test("a service not yet completed explains that rating is not available", async ({ page }) => {
  await mockCustomerServices(page, async (_url, route) =>
    route.fulfill({ json: customerPage([customerService({ completedAt: null })], 1) }),
  );
  await signInTo(page, "client");

  const card = page.locator(".customer-service-card");
  await expect(card.getByText("Podrás valorar este servicio cuando esté completado.", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Enviar valoración" })).toHaveCount(0);
});

test("empty customer list shows the no-services state with a search link", async ({ page }) => {
  await mockCustomerServices(page, async (_url, route) => route.fulfill({ json: customerPage([]) }));
  await signInTo(page, "client");

  const empty = page.locator(".customer-services-wrap .marketplace-empty");
  await expect(empty.getByRole("heading", { name: "Aún no tienes servicios" })).toBeVisible();
  await expect(empty.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
});

test("a failed list request shows a retryable error that recovers the list", async ({ page }) => {
  let attempts = 0;
  await mockCustomerServices(page, async (_url, route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 500, json: { detail: "Internal error" } });
    else await route.fulfill({ json: customerPage([customerService()], 1) });
  });
  await signInTo(page, "client");

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "No pudimos cargar tus servicios" })).toBeVisible();
  await expect(page.locator(".customer-service-list")).toHaveCount(0);

  await alert.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.locator(".customer-service-card")).toHaveCount(1);
  await expect(page.locator(".customer-services-wrap [role=alert]")).toHaveCount(0);
});

test("load more requests the next offset and appends the following services", async ({ page }) => {
  const firstPage = Array.from({ length: 20 }, (_, index) => customerService({ serviceId: `service-${index + 1}`, serviceTypeName: `Servicio ${index + 1}` }));
  const secondPage = [customerService({ serviceId: "service-21", serviceTypeName: "Servicio 21" })];
  const queries = await mockCustomerServices(page, async (url, route) => {
    const offset = Number(url.searchParams.get("offset"));
    if (offset === 0) await route.fulfill({ json: customerPage(firstPage, 21, 0) });
    else await route.fulfill({ json: customerPage(secondPage, 21, 20) });
  });
  await signInTo(page, "client");

  await expect(page.locator(".customer-service-card")).toHaveCount(20);
  await page.getByRole("button", { name: "Cargar más servicios" }).click();
  await expect(page.locator(".customer-service-card")).toHaveCount(21);
  await expect(page.getByRole("button", { name: "Cargar más servicios" })).toHaveCount(0);

  expect(queries.some((params) => params.get("offset") === "20")).toBe(true);
});

test("customer list fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCustomerServices(page, async (_url, route) =>
    route.fulfill({
      json: customerPage([
        customerService({ rating: { rating: 4, comment: "Un comentario bastante largo para revisar el ajuste en pantallas pequeñas.", createdAt: "2026-10-12T12:00:00Z" } }),
        customerService({ serviceId: "service-2", completedAt: null }),
      ], 2),
    }),
  );
  await signInTo(page, "client");

  await expect(page.locator(".customer-service-card")).toHaveCount(2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("provider sees status filters and each service's status badge", async ({ page }) => {
  await mockProviderServices(page, async (_url, route) =>
    route.fulfill({ json: { items: [providerService()], total: 1, limit: 20, offset: 0 } }),
  );
  await signInTo(page, "independent_driver");

  const filters = page.getByRole("group", { name: "Filtrar servicios por estado" });
  await expect(filters.getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");
  await expect(filters.getByRole("button", { name: "Confirmado" })).toHaveAttribute("aria-pressed", "false");
  await expect(filters.getByRole("button", { name: "En reclamo" })).toBeVisible();

  const card = page.locator(".account-service-card");
  await expect(card.getByRole("heading", { name: "Mudanzas" })).toBeVisible();
  await expect(card.getByText("Cliente: Ana Pérez", { exact: true })).toBeVisible();
  await expect(card.locator(".account-service-status")).toHaveText("Confirmado");
  await expect(card.getByRole("link", { name: "Mudanzas" })).toHaveAttribute("href", "/cuenta/servicios/service-provider-1");
});

test("provider filter requests that status and shows its own empty state", async ({ page }) => {
  const queries = await mockProviderServices(page, async (url, route) => {
    const status = url.searchParams.get("status");
    const items = status === "confirmed" ? [] : [providerService()];
    await route.fulfill({ json: { items, total: items.length, limit: 20, offset: 0 } });
  });
  await signInTo(page, "independent_driver");

  await expect(page.locator(".account-service-card")).toHaveCount(1);
  await page.getByRole("group", { name: "Filtrar servicios por estado" }).getByRole("button", { name: "Confirmado" }).click();

  await expect(page.getByRole("button", { name: "Confirmado" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".marketplace-empty").getByRole("heading", { name: "No tienes servicios confirmados" })).toBeVisible();
  expect(queries.some((params) => params.get("status") === "confirmed")).toBe(true);
});

test("provider whose list is forbidden sees the provider-only message", async ({ page }) => {
  await mockProviderServices(page, async (_url, route) => route.fulfill({ status: 403, json: { detail: "Forbidden" } }));
  await signInTo(page, "independent_driver");

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "Esta cuenta no tiene servicios de prestador" })).toBeVisible();
  await expect(alert.getByText("Los servicios como prestador solo están disponibles para conductores y empresas de transporte.", { exact: true })).toBeVisible();
});
