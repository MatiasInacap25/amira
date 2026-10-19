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

function chat(overrides: Record<string, unknown> = {}) {
  return {
    chatId: "chat-1",
    requestId: "request-1",
    createdAt: "2026-10-10T00:00:00Z",
    serviceName: "Mudanzas",
    originCommuneName: "Santiago",
    destinationCommuneName: "Valparaíso",
    counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null },
    lastMessage: null,
    unreadCount: 0,
    ...overrides,
  };
}

// Answers GET /api/chats/unread with the given total.
function unreadTotal(total: number) {
  return async (route: Route) => route.fulfill({ json: { total } });
}

function chatPage(items: unknown[], total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-cuenta-servicios.spec.ts.
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

// Signs in through the real login form and lands on /mensajes. The real-time stream answers with `events`.
async function signInToMessages(
  page: Page,
  events: (route: Route) => Promise<void> = idleEventStream,
  unread: (route: Route) => Promise<void> = unreadTotal(0),
) {
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/chats/events", events);
  await page.route("**/api/chats/unread", unread);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "customer", profile_id: null } }),
  );
  await page.goto("/login?next=%2Fmensajes");
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/mensajes$/);
}

// Answers GET /api/chats with the handler and records every query string it receives.
async function mockChats(page: Page, respond: (url: URL, route: Route) => Promise<void>) {
  const queries: URLSearchParams[] = [];
  await page.route("**/api/chats?*", async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    await respond(url, route);
  });
  return queries;
}

// A stream with no events: one keepalive comment, then the server closes it.
async function idleEventStream(route: Route) {
  await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": keepalive\n\n" });
}

test("a message.created event refetches the chat list and shows the new last message", async ({ page }) => {
  let listRequests = 0;
  let eventSent = false;
  const streamUrls: string[] = [];
  const streamAuthorization: string[] = [];
  await mockChats(page, async (_url, route) => {
    listRequests += 1;
    const preview = eventSent ? "Nuevo mensaje en vivo" : "Primer mensaje";
    await route.fulfill({
      json: chatPage([chat({ lastMessage: { content: preview, sentAt: new Date().toISOString(), fromMe: false } })]),
    });
  });
  await signInToMessages(page, async (route) => {
    streamUrls.push(route.request().url());
    streamAuthorization.push(route.request().headers().authorization ?? "");
    await expect.poll(() => listRequests).toBeGreaterThanOrEqual(1);
    eventSent = true;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: message.created\ndata: {"kind":"message.created","chatId":"chat-1","messageId":"message-2"}\n\n',
    });
  });

  await expect(page.getByText("Nuevo mensaje en vivo")).toBeVisible();
  await expect.poll(() => listRequests).toBeGreaterThanOrEqual(2);
  expect(new URL(streamUrls[0]).pathname).toMatch(/\/api\/chats\/events$/);
  expect(new URL(streamUrls[0]).search).toBe("");
  expect(streamAuthorization[0]).toMatch(/^Bearer eyJ/);
});

test("signed-out visitor sees a sign-in prompt and no chat list is requested", async ({ page }) => {
  const queries = await mockChats(page, async (_url, route) => route.fulfill({ json: chatPage([]) }));

  await page.goto("/mensajes");

  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert).toHaveText("Inicia sesión para ver tus mensajes.");
  await expect(alert.locator("xpath=..").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
    "href",
    "/login?next=%2Fmensajes",
  );
  await expect(page.getByRole("heading", { level: 1, name: "Mensajes" })).toBeVisible();
  expect(queries).toHaveLength(0);
});

test("signed-in list shows counterpart kind, service, route and the last message preview", async ({ page }) => {
  const sentAt = new Date(Date.now() - 5 * 60_000).toISOString();
  await mockChats(page, async (_url, route) =>
    route.fulfill({
      json: chatPage([
        chat({
          chatId: "chat-customer",
          counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null },
          lastMessage: { content: "¿A qué hora llegan?", sentAt, fromMe: false },
        }),
        chat({
          chatId: "chat-company",
          serviceName: "Fletes",
          destinationCommuneName: null,
          counterpart: { name: "Transportes Andes", kind: "company", providerProfileId: "provider-1" },
          lastMessage: { content: "Confirmamos el horario", sentAt, fromMe: true },
        }),
        chat({
          chatId: "chat-driver",
          serviceName: "Traslado",
          counterpart: { name: "Luis Soto", kind: "independent_driver", providerProfileId: "provider-2" },
        }),
      ]),
    }),
  );

  await signInToMessages(page);

  const customer = page.getByRole("article", { name: "Ana Pérez" });
  await expect(customer.getByText("Cliente · Mudanzas")).toBeVisible();
  await expect(customer.getByText("Santiago → Valparaíso")).toBeVisible();
  await expect(customer.getByText("¿A qué hora llegan?")).toBeVisible();
  await expect(customer.getByRole("time")).toHaveText("hace 5 min");
  await expect(customer.getByRole("link")).toHaveAttribute("href", "/mensajes/chat-customer");

  const company = page.getByRole("article", { name: "Transportes Andes" });
  await expect(company.getByText("Empresa · Fletes")).toBeVisible();
  await expect(company.getByText("Santiago → Destino no indicado")).toBeVisible();
  await expect(company.getByText("Tú: Confirmamos el horario")).toBeVisible();
  await expect(company.getByRole("link")).toHaveAttribute("href", "/mensajes/chat-company");

  const driver = page.getByRole("article", { name: "Luis Soto" });
  await expect(driver.getByText("Conductor independiente · Traslado")).toBeVisible();
  await expect(driver.getByText("Sin mensajes aún")).toBeVisible();
  await expect(driver.getByRole("time")).toHaveCount(0);
});

test("empty chat list explains that conversations appear after an accepted request", async ({ page }) => {
  await mockChats(page, async (_url, route) => route.fulfill({ json: chatPage([]) }));

  await signInToMessages(page);

  const empty = page.getByRole("main").getByRole("status").filter({ hasText: "Aún no tienes conversaciones" });
  await expect(empty.getByRole("heading", { name: "Aún no tienes conversaciones" })).toBeVisible();
  await expect(empty.getByText("Cuando una solicitud sea aceptada, la conversación aparecerá aquí.")).toBeVisible();
  await expect(page.getByRole("list")).toHaveCount(0);
});

test("a failed chat request shows an error that retries and then loads the list", async ({ page }) => {
  let attempts = 0;
  await mockChats(page, async (_url, route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 500, json: { detail: { type: "internal", msg: "boom" } } });
      return;
    }
    await route.fulfill({ json: chatPage([chat({ counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null } })]) });
  });

  await signInToMessages(page);

  const error = page.getByRole("main").getByRole("alert");
  await expect(error.getByText("No pudimos cargar tus mensajes. Inténtalo nuevamente.")).toBeVisible();
  await error.getByRole("button", { name: "Reintentar" }).click();

  await expect(page.getByRole("article", { name: "Ana Pérez" })).toBeVisible();
  await expect(error).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("load more appends the next page and hides the button when no pages remain", async ({ page }) => {
  const firstPage = Array.from({ length: 20 }, (_, index) =>
    chat({ chatId: `chat-${index}`, counterpart: { name: `Contacto ${index}`, kind: "customer", providerProfileId: null } }),
  );
  const secondPage = [
    chat({ chatId: "chat-20", counterpart: { name: "Contacto 20", kind: "customer", providerProfileId: null } }),
  ];
  const queries = await mockChats(page, async (url, route) => {
    const offset = Number(url.searchParams.get("offset"));
    await route.fulfill({ json: offset === 0 ? chatPage(firstPage, 21, 0) : chatPage(secondPage, 21, offset) });
  });

  await signInToMessages(page);

  await expect(page.getByRole("article")).toHaveCount(20);
  const loadMore = page.getByRole("button", { name: "Cargar más" });
  await loadMore.click();

  await expect(page.getByRole("article", { name: "Contacto 20" })).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(21);
  await expect(loadMore).toHaveCount(0);
  expect(queries.map((params) => params.get("offset"))).toEqual(expect.arrayContaining(["0", "20"]));
});

test("chat list fits a phone-width viewport without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockChats(page, async (_url, route) =>
    route.fulfill({
      json: chatPage([
        chat({
          counterpart: { name: "Ana Pérez con un nombre bastante largo para forzar el ajuste", kind: "customer", providerProfileId: null },
          lastMessage: {
            content: "Mensaje largo sin espacios para verificar que el texto no empuje el ancho de la página más allá del viewport",
            sentAt: "2026-10-10T00:00:00Z",
            fromMe: false,
          },
        }),
      ]),
    }),
  );

  await signInToMessages(page);
  await expect(page.getByRole("article")).toHaveCount(1);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("list shows each chat's unread count in its row and the navigation badge shows the total", async ({ page }) => {
  await mockChats(page, async (_url, route) =>
    route.fulfill({
      json: chatPage([
        chat({ chatId: "chat-ana", counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null }, unreadCount: 3 }),
        chat({ chatId: "chat-luis", counterpart: { name: "Luis Soto", kind: "company", providerProfileId: "p-2" }, unreadCount: 0 }),
      ]),
    }),
  );
  await signInToMessages(page, idleEventStream, unreadTotal(3));

  const anaRow = page.locator(".chat-card", { hasText: "Ana Pérez" });
  await expect(anaRow.getByLabel("3 mensajes sin leer")).toHaveText("3");
  await expect(anaRow).toHaveClass(/chat-card-unread/);
  const luisRow = page.locator(".chat-card", { hasText: "Luis Soto" });
  await expect(luisRow.getByLabel(/mensajes? sin leer/)).toHaveCount(0);
  await expect(luisRow).not.toHaveClass(/chat-card-unread/);
  await expect(page.locator(".desktop-nav").getByLabel("3 mensajes sin leer")).toHaveText("3");
});

test("a chat.read event from the stream refreshes the navigation badge", async ({ page }) => {
  let total = 4;
  let unreadRequests = 0;
  await signInToMessages(
    page,
    async (route) => {
      await expect.poll(() => unreadRequests).toBeGreaterThanOrEqual(1);
      total = 0;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: 'event: chat.read\ndata: {"kind":"chat.read","chatId":"chat-1"}\n\n',
      });
    },
    async (route) => {
      unreadRequests += 1;
      await route.fulfill({ json: { total } });
    },
  );

  await expect(page.locator(".desktop-nav").getByLabel("4 mensajes sin leer")).toBeVisible();
  await expect(page.locator(".desktop-nav .nav-badge")).toHaveCount(0);
});

test("a message.created event refreshes the navigation badge total", async ({ page }) => {
  let total = 1;
  let unreadRequests = 0;
  await signInToMessages(
    page,
    async (route) => {
      await expect.poll(() => unreadRequests).toBeGreaterThanOrEqual(1);
      total = 2;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: 'event: message.created\ndata: {"kind":"message.created","chatId":"chat-1","messageId":"message-2"}\n\n',
      });
    },
    async (route) => {
      unreadRequests += 1;
      await route.fulfill({ json: { total } });
    },
  );

  await expect(page.locator(".desktop-nav").getByLabel("2 mensajes sin leer")).toBeVisible();
});

test("signed-out pages make no unread-total request", async ({ page }) => {
  const unreadRequests: string[] = [];
  await page.route("**/api/chats/unread", async (route) => {
    unreadRequests.push(route.request().url());
    await route.fulfill({ json: { total: 5 } });
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: "Mensajes" })).toHaveCount(0);
  await page.goto("/mensajes");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("Inicia sesión para ver tus mensajes.");

  expect(unreadRequests).toHaveLength(0);
});
