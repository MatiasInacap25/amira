import { expect, test, type Page, type Route } from "@playwright/test";
import { locationsResponse } from "./support/catalog-fixtures";

const requestPath = "/solicitudes/request-provider-1";
const chatPath = "/mensajes/chat-provider-1";
const dateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" });

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

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-solicitudes.spec.ts.
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
  await page.goto(`/login?next=${encodeURIComponent(requestPath)}`);
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(new RegExp(`${requestPath}$`));
}

type DetailResponder = (route: Route, method: string) => Promise<void>;

// Answers every /api/provider/requests/{id}[/accept|/reject] call with the handler and records each request.
async function mockProviderRequest(page: Page, respond: DetailResponder) {
  const calls: Array<{ method: string; path: string; authorization?: string }> = [];
  await page.route("**/api/provider/requests/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({ method: request.method(), path: url.pathname, authorization: request.headers()["authorization"] });
    await respond(route, request.method());
  });
  return calls;
}

function fact(page: Page, label: string) {
  return page.locator(".provider-request-facts > div").filter({ has: page.locator("dt", { hasText: label }) }).locator("dd");
}

// Cargo facts live in the "Detalle de la carga" panel, separate from the summary list.
function cargoTerms(page: Page) {
  return page.locator(".provider-request-panel", { has: page.getByRole("heading", { name: "Detalle de la carga" }) }).locator("dt");
}

test("signed-out visitor is asked to sign in with a return link to this request", async ({ page }) => {
  const calls = await mockProviderRequest(page, async (route) => route.fulfill({ json: providerRequest() }));

  await page.goto(requestPath);

  const alert = page.locator(".provider-request-detail [role=alert]");
  await expect(alert).toHaveText("Inicia sesión con tu correo confirmado para ver las solicitudes.");
  await expect(page.locator("#contenido").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", `/login?next=${encodeURIComponent(requestPath)}`);
  expect(calls).toHaveLength(0);
});

test("pending request shows route, service, requested dates, first-name customer and cargo details", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({ json: providerRequest() }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Santiago, Metropolitana de Santiago → Valparaíso, Valparaíso");
  await expect(page.locator(".provider-request-card-heading .eyebrow")).toHaveText("Mudanzas");
  await expect(page.locator(".provider-request-status")).toHaveText("Pendiente");

  await expect(fact(page, "Origen")).toHaveText("Santiago, Metropolitana de Santiago");
  await expect(fact(page, "Destino")).toHaveText("Valparaíso, Valparaíso");
  await expect(fact(page, "Cliente")).toHaveText("Camila");
  await expect(fact(page, "Modalidad")).toHaveText("Servicio compartido");
  await expect(fact(page, "Fecha solicitada")).toHaveText(dateFormatter.format(new Date("2026-10-12T12:00:00Z")));
  await expect(fact(page, "Recibida")).toHaveText(dateFormatter.format(new Date("2026-10-01T12:00:00Z")));
  await expect(page.getByText("Verás el apellido del cliente después de aceptar la solicitud.")).toBeVisible();

  await expect(fact(page, "Descripción")).toHaveText("Retiro de muebles.");
  await expect(fact(page, "Medidas")).toHaveText("2 x 1 x 1 m");
  await expect(fact(page, "Peso estimado")).toHaveText("250.5 kg");
  await expect(cargoTerms(page).filter({ hasText: "Volumen estimado" })).toHaveCount(0);
});

test("pending request offers reject and accept actions, and a back link to the inbox", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({ json: providerRequest() }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.getByRole("button", { name: "Rechazar" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Aceptar y abrir chat" })).toBeEnabled();
  await expect(page.getByRole("link", { name: "Abrir chat" })).toHaveCount(0);
  await expect(page.getByText("Solicitud cerrada")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Volver a solicitudes" })).toHaveAttribute("href", "/solicitudes");
});

test("accepted request shows the full customer name and opens its chat instead of decision actions", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({
    json: providerRequest({ status: "accepted", customerLastName: "Rojas", chatId: "chat-provider-1" }),
  }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.locator(".provider-request-status")).toHaveText("Aceptada");
  await expect(fact(page, "Cliente")).toHaveText("Camila Rojas");
  await expect(page.getByText("Verás el apellido del cliente después de aceptar la solicitud.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Aceptar y abrir chat" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Abrir chat" })).toHaveAttribute("href", chatPath);
});

test("request without a commune falls back to the free-text address and says no cargo details were given", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({
    json: providerRequest({
      originCommuneName: null,
      originRegionName: null,
      isExclusive: true,
      description: null,
      cargoMeasurements: null,
      estimatedWeight: null,
      estimatedVolume: "3.5",
    }),
  }));
  await signInAsSmsVerifiedProvider(page);

  await expect(fact(page, "Origen")).toHaveText("Calle Uno 123");
  await expect(fact(page, "Modalidad")).toHaveText("Servicio exclusivo");
  await expect(fact(page, "Volumen estimado")).toHaveText("3.5 m³");
  await expect(cargoTerms(page).filter({ hasText: "Peso estimado" })).toHaveCount(0);
});

test("request with no cargo details shows the empty-cargo message", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({
    json: providerRequest({ description: null, cargoMeasurements: null, estimatedWeight: null, estimatedVolume: null }),
  }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.getByText("El cliente no especificó detalles de la carga.")).toBeVisible();
  await expect(cargoTerms(page)).toHaveCount(0);
});

test("accepting sends the verified token, disables both actions while saving, and opens the new chat", async ({ page }) => {
  let releaseAccept!: () => void;
  const acceptGate = new Promise<void>((resolve) => { releaseAccept = resolve; });
  const calls = await mockProviderRequest(page, async (route, method) => {
    if (method === "GET") {
      await route.fulfill({ json: providerRequest() });
      return;
    }
    await acceptGate;
    await route.fulfill({ json: { requestId: "request-provider-1", status: "accepted", chatId: "chat-provider-1" } });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("button", { name: "Aceptar y abrir chat" }).click();
  await expect(page.getByRole("button", { name: "Guardando…" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Rechazar" })).toBeDisabled();

  releaseAccept();
  await expect(page).toHaveURL(new RegExp(`${chatPath}$`));
  expect(calls.find((call) => call.method === "POST")).toMatchObject({
    path: "/api/provider/requests/request-provider-1/accept",
    authorization: `Bearer ${accessToken("aal2", "verified-aal2-token")}`,
  });
});

test("rejecting closes the request in place once the refreshed request reports it rejected", async ({ page }) => {
  let rejected = false;
  const calls = await mockProviderRequest(page, async (route, method) => {
    if (method === "GET") {
      await route.fulfill({ json: providerRequest({ status: rejected ? "rejected" : "pending" }) });
      return;
    }
    rejected = true;
    await route.fulfill({ json: { requestId: "request-provider-1", status: "rejected", chatId: null } });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("button", { name: "Rechazar" }).click();
  await expect(page.locator(".provider-request-status")).toHaveText("Rechazada");
  await expect(page.getByText("Solicitud cerrada")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Abrir chat" })).toHaveCount(0);
  expect(calls.some((call) => call.method === "POST" && call.path.endsWith("/reject"))).toBe(true);
});

test("a conflicting decision tells the provider to refresh and keeps the actions available", async ({ page }) => {
  await mockProviderRequest(page, async (route, method) => {
    if (method === "GET") await route.fulfill({ json: providerRequest() });
    else await route.fulfill({ status: 409, json: { detail: "Already decided" } });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("button", { name: "Rechazar" }).click();
  await expect(page.locator(".provider-request-detail [role=alert]")).toHaveText("La solicitud ya fue respondida. Actualiza la página.");
  await expect(page.getByRole("button", { name: "Rechazar" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Aceptar y abrir chat" })).toBeEnabled();
});

test("a provider-role rejection on decision explains that this account cannot manage requests", async ({ page }) => {
  await mockProviderRequest(page, async (route, method) => {
    if (method === "GET") await route.fulfill({ json: providerRequest() });
    else await route.fulfill({ status: 403, json: { detail: "Forbidden" } });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("button", { name: "Aceptar y abrir chat" }).click();
  await expect(page.locator(".provider-request-detail [role=alert]")).toHaveText("Esta cuenta no puede administrar solicitudes de prestadores.");
  await expect(page).toHaveURL(new RegExp(`${requestPath}$`));
});

test("a server failure on decision shows a generic retry message without changing the request", async ({ page }) => {
  await mockProviderRequest(page, async (route, method) => {
    if (method === "GET") await route.fulfill({ json: providerRequest() });
    else await route.fulfill({ status: 503, json: { detail: "Temporary failure" } });
  });
  await signInAsSmsVerifiedProvider(page);

  await page.getByRole("button", { name: "Aceptar y abrir chat" }).click();
  await expect(page.locator(".provider-request-detail [role=alert]")).toHaveText("No pudimos responder la solicitud. Inténtalo nuevamente.");
  await expect(page.locator(".provider-request-status")).toHaveText("Pendiente");
  await expect(page.getByRole("button", { name: "Aceptar y abrir chat" })).toBeEnabled();
});

test("an unknown request shows the unavailable state and no decision actions", async ({ page }) => {
  await mockProviderRequest(page, async (route) => route.fulfill({ status: 404, json: { detail: "Not found" } }));
  await signInAsSmsVerifiedProvider(page);

  const alert = page.locator(".provider-request-detail [role=alert]");
  await expect(alert.getByRole("heading", { name: "Solicitud no disponible" })).toBeVisible();
  await expect(alert.getByText("La solicitud ya no está disponible para este perfil.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(0);
});

test("a failed request load shows a retryable error that recovers the detail", async ({ page }) => {
  let attempts = 0;
  await mockProviderRequest(page, async (route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 500, json: { detail: "Internal error" } });
    else await route.fulfill({ json: providerRequest() });
  });
  await signInAsSmsVerifiedProvider(page);

  const alert = page.locator(".provider-request-detail [role=alert]");
  await expect(alert).toContainText("No pudimos cargar la solicitud. Inténtalo nuevamente.");
  await expect(page.getByRole("button", { name: "Rechazar" })).toHaveCount(0);

  await alert.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Santiago, Metropolitana de Santiago → Valparaíso, Valparaíso");
  await expect(page.locator(".provider-request-detail [role=alert]")).toHaveCount(0);
});

test("request detail fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockProviderRequest(page, async (route) => route.fulfill({ json: providerRequest() }));
  await signInAsSmsVerifiedProvider(page);

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
