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

function chatHeader(overrides: Record<string, unknown> = {}) {
  return {
    chatId: "chat-1",
    requestId: "request-1",
    createdAt: "2026-10-10T00:00:00Z",
    serviceName: "Mudanzas",
    originCommuneName: "Santiago",
    destinationCommuneName: "Valparaíso",
    counterpart: { name: "Ana Pérez", kind: "customer", providerProfileId: null },
    ...overrides,
  };
}

function threadPage(overrides: Record<string, unknown> = {}) {
  return {
    ...chatHeader(),
    timeline: [],
    nextBefore: null,
    viewerRole: "customer",
    ...overrides,
  };
}

function messageEntry(messageId: string, content: string, fromMe: boolean, senderName: string) {
  return { kind: "message", messageId, content, sentAt: "2026-10-10T12:00:00Z", fromMe, senderName };
}

function quotationEntry(overrides: Record<string, unknown> = {}) {
  return {
    kind: "quotation",
    quotation: {
      quotationId: "quotation-1",
      status: "pending",
      amount: 125000,
      currency: "CLP",
      serviceAt: "2099-12-30T12:00:00.000Z",
      description: "Mudanza de dos ambientes",
      expiresAt: "2099-12-31T12:00:00.000Z",
      createdAt: "2026-10-10T12:00:00Z",
      paidAt: null,
      ...overrides,
    },
  };
}

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-mensajes.spec.ts.
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

// Signs in through the real login form and lands on the given conversation.
async function signInToChat(
  page: Page,
  role: "customer" | "provider",
  chatId = "chat-1",
  events: (route: Route) => Promise<void> = idleEventStream,
) {
  await mockSmsVerifiedAuth(page);
  await mockChatEvents(page, events);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({
      json: { user_id: "account-test-1", role, profile_id: role === "provider" ? "provider-1" : null },
    }),
  );
  await page.goto(`/login?next=${encodeURIComponent(`/mensajes/${chatId}`)}`);
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(new RegExp(`/mensajes/${chatId}$`));
}

// Every request to the thread endpoint (GET history, POST message) goes to the handler.
async function mockThread(page: Page, handler: (route: Route) => Promise<void>) {
  await page.route("**/api/chats/chat-1/messages*", handler);
}

// The real-time stream (GET /api/chats/events) answers with the handler.
async function mockChatEvents(page: Page, handler: (route: Route) => Promise<void>) {
  await page.route("**/api/chats/events", handler);
}

// A stream with no events: one keepalive comment, then the server closes it.
async function idleEventStream(route: Route) {
  await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": keepalive\n\n" });
}

test("a message.created event refetches the open thread and shows the new message", async ({ page }) => {
  let threadRequests = 0;
  let eventSent = false;
  const streamUrls: string[] = [];
  const streamAuthorization: string[] = [];
  const first = messageEntry("message-1", "Hola, ¿mudanza confirmada?", false, "Ana Pérez");
  const second = messageEntry("message-2", "¿Llegas a las 10?", false, "Ana Pérez");

  await mockThread(page, async (route) => {
    threadRequests += 1;
    await route.fulfill({ json: threadPage({ timeline: eventSent ? [first, second] : [first] }) });
  });
  await signInToChat(page, "customer", "chat-1", async (route) => {
    streamUrls.push(route.request().url());
    streamAuthorization.push(route.request().headers().authorization ?? "");
    await expect.poll(() => threadRequests).toBeGreaterThanOrEqual(1);
    eventSent = true;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: message.created\ndata: {"kind":"message.created","chatId":"chat-1","messageId":"message-2"}\n\n',
    });
  });

  await expect(page.getByText("¿Llegas a las 10?")).toBeVisible();
  await expect.poll(() => threadRequests).toBeGreaterThanOrEqual(2);
  expect(new URL(streamUrls[0]).pathname).toMatch(/\/api\/chats\/events$/);
  expect(new URL(streamUrls[0]).search).toBe("");
  expect(streamUrls[0]).not.toContain("verified-aal2-token");
  expect(streamAuthorization[0]).toBe(`Bearer ${accessToken("aal2", "verified-aal2-token")}`);
});

test("a keepalive-only stream keeps the thread polling every 10 s", async ({ page }) => {
  test.setTimeout(90_000);
  let threadRequests = 0;
  await mockThread(page, async (route) => {
    threadRequests += 1;
    await route.fulfill({ json: threadPage({ timeline: [messageEntry("message-1", "Hola", false, "Ana Pérez")] }) });
  });
  await signInToChat(page, "customer", "chat-1", idleEventStream);

  await expect.poll(() => threadRequests).toBeGreaterThanOrEqual(1);
  const afterOpen = threadRequests;
  // The stream was accepted but never reported ready, so the fallback poll must keep running.
  await expect.poll(() => threadRequests, { timeout: 30_000 }).toBeGreaterThanOrEqual(afterOpen + 2);
});

test("a ready event stops the 10 s fallback poll", async ({ page }) => {
  test.setTimeout(90_000);
  let threadRequests = 0;
  await mockThread(page, async (route) => {
    threadRequests += 1;
    await route.fulfill({ json: threadPage({ timeline: [messageEntry("message-1", "Hola", false, "Ana Pérez")] }) });
  });
  await signInToChat(page, "customer", "chat-1", async (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: "event: ready\ndata: {}\n\n" }),
  );

  await expect.poll(() => threadRequests).toBeGreaterThanOrEqual(1);
  const afterReady = threadRequests;
  // A fulfilled route ends the body, so the client reconnects; while it reports ready, no interval poll fires.
  await page.waitForTimeout(11_000);
  expect(threadRequests).toBe(afterReady);
});

test("signed-in customer opens the thread with counterpart, route and messages oldest first", async ({ page }) => {
  await mockThread(page, async (route) =>
    route.fulfill({
      json: threadPage({
        timeline: [
          messageEntry("message-1", "¿A qué hora llegan?", false, "Ana Pérez"),
          messageEntry("message-2", "Llegamos a las 9", true, "Tú"),
        ],
      }),
    }),
  );

  await signInToChat(page, "customer");

  await expect(page.getByRole("heading", { level: 1, name: "Ana Pérez" })).toBeVisible();
  await expect(page.getByText("Cliente · Mudanzas")).toBeVisible();
  await expect(page.getByText("Santiago → Valparaíso")).toBeVisible();

  const messages = page.getByRole("list", { name: "Mensajes" }).getByRole("listitem");
  await expect(messages).toHaveCount(2);
  await expect(messages.nth(0)).toContainText("¿A qué hora llegan?");
  await expect(messages.nth(1)).toContainText("Llegamos a las 9");
  await expect(messages.nth(0).getByText("Ana Pérez")).toBeVisible();
  await expect(messages.nth(1).getByText("Ana Pérez")).toHaveCount(0);
  await expect(messages.nth(0).getByRole("time")).toHaveAttribute("datetime", "2026-10-10T12:00:00Z");
});

test("signed-out visitor is asked to sign in instead of seeing an empty conversation", async ({ page }) => {
  const requests: string[] = [];
  await mockThread(page, async (route) => {
    requests.push(route.request().url());
    await route.fulfill({ json: threadPage() });
  });

  await page.goto("/mensajes/chat-1");

  const prompt = page.getByRole("main").getByRole("alert");
  await expect(prompt).toHaveText("Inicia sesión con tu correo confirmado para ver tus mensajes.");
  await expect(prompt.locator("xpath=..").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
    "href",
    "/login?next=%2Fmensajes%2Fchat-1",
  );
  expect(requests).toHaveLength(0);
});

test("back link returns to the chat list", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage() }));

  await signInToChat(page, "customer");

  await expect(page.getByRole("link", { name: "Volver a mensajes" })).toHaveAttribute("href", "/mensajes");
});

test("empty thread explains that no messages exist yet and offers no list", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage() }));

  await signInToChat(page, "customer");

  await expect(page.getByRole("heading", { name: "Aún no hay mensajes en esta conversación" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Mensajes" })).toHaveCount(0);
});

test("unknown conversation shows a not-found state that links back to the list", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ status: 404, json: { detail: { type: "not_found", msg: "missing" } } }));

  await signInToChat(page, "customer");

  const notFound = page.getByRole("main").getByRole("status");
  await expect(notFound.getByRole("heading", { level: 1, name: "No encontramos esta conversación" })).toBeVisible();
  await expect(notFound.getByText("Es posible que ya no exista o que no tengas acceso a ella.")).toBeVisible();
  await expect(notFound.getByRole("link", { name: "Ver mis mensajes" })).toHaveAttribute("href", "/mensajes");
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});

test("a failed thread request shows an error that retries and then loads the messages", async ({ page }) => {
  let attempts = 0;
  await mockThread(page, async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 500, json: { detail: { type: "internal", msg: "boom" } } });
      return;
    }
    await route.fulfill({ json: threadPage({ timeline: [messageEntry("message-1", "Hola de nuevo", false, "Ana Pérez")] }) });
  });

  await signInToChat(page, "customer");

  const error = page.getByRole("main").getByRole("alert");
  await expect(error.getByText("No pudimos cargar tus mensajes. Inténtalo nuevamente.")).toBeVisible();
  await error.getByRole("button", { name: "Reintentar" }).click();

  await expect(page.getByRole("list", { name: "Mensajes" }).getByText("Hola de nuevo")).toBeVisible();
  await expect(error).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("load older messages prepends the previous page and hides the button when none remain", async ({ page }) => {
  const befores: (string | null)[] = [];
  await mockThread(page, async (route) => {
    const before = new URL(route.request().url()).searchParams.get("before");
    befores.push(before);
    if (before === null) {
      await route.fulfill({
        json: threadPage({
          timeline: [messageEntry("message-2", "Segundo mensaje", false, "Ana Pérez")],
          nextBefore: "cursor-older",
        }),
      });
      return;
    }
    await route.fulfill({ json: threadPage({ timeline: [messageEntry("message-1", "Primer mensaje", false, "Ana Pérez")] }) });
  });

  await signInToChat(page, "customer");

  const messages = page.getByRole("list", { name: "Mensajes" }).getByRole("listitem");
  await expect(messages).toHaveCount(1);
  await page.getByRole("button", { name: "Ver mensajes anteriores" }).click();

  await expect(messages).toHaveCount(2);
  await expect(messages.nth(0)).toContainText("Primer mensaje");
  await expect(messages.nth(1)).toContainText("Segundo mensaje");
  await expect(page.getByRole("button", { name: "Ver mensajes anteriores" })).toHaveCount(0);
  expect(befores).toContain("cursor-older");
});

test("composer shows the character count and keeps send disabled until there is text", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage() }));

  await signInToChat(page, "customer");

  const send = page.getByRole("button", { name: "Enviar", exact: true });
  await expect(page.getByRole("textbox", { name: "Escribe un mensaje" })).toBeVisible();
  await expect(page.getByText("0/2000")).toBeVisible();
  await expect(send).toBeDisabled();

  await page.getByRole("textbox", { name: "Escribe un mensaje" }).fill("Hola");
  await expect(page.getByText("4/2000")).toBeVisible();
  await expect(send).toBeEnabled();
});

test("sending a message posts the trimmed text, clears the composer and shows the new message", async ({ page }) => {
  let sent = false;
  const bodies: unknown[] = [];
  await mockThread(page, async (route) => {
    if (route.request().method() === "POST") {
      bodies.push(route.request().postDataJSON());
      sent = true;
      await route.fulfill({
        json: { messageId: "message-new", content: "Llego a las 9", sentAt: "2026-10-10T12:05:00Z", fromMe: true, senderName: "Tú" },
      });
      return;
    }
    await route.fulfill({
      json: threadPage({ timeline: sent ? [messageEntry("message-new", "Llego a las 9", true, "Tú")] : [] }),
    });
  });

  await signInToChat(page, "customer");

  const composer = page.getByRole("textbox", { name: "Escribe un mensaje" });
  await composer.fill("  Llego a las 9  ");
  await page.getByRole("button", { name: "Enviar", exact: true }).click();

  await expect(page.getByRole("list", { name: "Mensajes" }).getByText("Llego a las 9")).toBeVisible();
  await expect(composer).toHaveValue("");
  expect(bodies).toEqual([{ content: "Llego a las 9" }]);
});

test("contact details are blocked before sending for phone, email, link and social handle", async ({ page }) => {
  const posts: string[] = [];
  await mockThread(page, async (route) => {
    if (route.request().method() === "POST") {
      posts.push(route.request().url());
      await route.fulfill({ json: {} });
      return;
    }
    await route.fulfill({ json: threadPage() });
  });

  await signInToChat(page, "customer");

  const composer = page.getByRole("textbox", { name: "Escribe un mensaje" });
  const error = page.locator(".chat-composer").getByRole("alert");
  const cases = [
    ["Llámame al +56 9 1234 5678", "No compartas números de teléfono en el chat."],
    ["Escríbeme a ana@example.test", "No compartas correos electrónicos en el chat."],
    ["Mira www.ejemplo.cl", "No compartas enlaces en el chat."],
    ["Búscame en @anaperez_123", "No compartas redes sociales en el chat."],
  ] as const;

  for (const [draft, message] of cases) {
    await composer.fill(draft);
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
    await expect(error).toHaveText(message);
    await expect(composer).toHaveValue(draft);
  }
  expect(posts).toHaveLength(0);
});

test("backend contact-filter rejection shows its message verbatim and keeps the draft", async ({ page }) => {
  await mockThread(page, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 422,
        json: { detail: [{ type: "contact_details_blocked", msg: "El chat no permite compartir datos de contacto." }] },
      });
      return;
    }
    await route.fulfill({ json: threadPage() });
  });

  await signInToChat(page, "customer");

  const composer = page.getByRole("textbox", { name: "Escribe un mensaje" });
  await composer.fill("Nos vemos en la plaza");
  await page.getByRole("button", { name: "Enviar", exact: true }).click();

  await expect(page.locator(".chat-composer").getByRole("alert")).toHaveText("El chat no permite compartir datos de contacto.");
  await expect(composer).toHaveValue("Nos vemos en la plaza");
});

test("a failed send shows a retry message and keeps the draft", async ({ page }) => {
  await mockThread(page, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 500, json: { detail: { type: "internal", msg: "boom" } } });
      return;
    }
    await route.fulfill({ json: threadPage() });
  });

  await signInToChat(page, "customer");

  const composer = page.getByRole("textbox", { name: "Escribe un mensaje" });
  await composer.fill("Mensaje que no debe perderse");
  await page.getByRole("button", { name: "Enviar", exact: true }).click();

  await expect(page.locator(".chat-composer").getByRole("alert")).toHaveText(
    "No pudimos enviar el mensaje. Revisa tu conexión e inténtalo nuevamente.",
  );
  await expect(composer).toHaveValue("Mensaje que no debe perderse");
});

test("customer cannot open the quotation dialog", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ viewerRole: "customer" }) }));

  await signInToChat(page, "customer");

  await expect(page.getByRole("heading", { level: 1, name: "Ana Pérez" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Enviar cotización" })).toHaveCount(0);
});

test("provider validates an empty quotation before sending", async ({ page }) => {
  const posts: string[] = [];
  await mockThread(page, async (route) => {
    if (route.request().method() === "POST") posts.push(route.request().url());
    await route.fulfill({ json: threadPage({ viewerRole: "provider" }) });
  });
  await page.route("**/api/chats/chat-1/quotations", async (route) => {
    posts.push(route.request().url());
    await route.fulfill({ json: {} });
  });

  await signInToChat(page, "provider");

  await page.getByRole("button", { name: "Enviar cotización" }).click();
  const dialog = page.getByRole("dialog", { name: "Envía tu cotización" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Enviar cotización" }).click();

  await expect(dialog.getByRole("alert")).toHaveText("Ingresa un monto mayor a cero.");
  expect(posts).toHaveLength(0);
});

test("provider sends a quotation with the entered terms and the dialog closes", async ({ page }) => {
  const bodies: Record<string, unknown>[] = [];
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ viewerRole: "provider" }) }));
  await page.route("**/api/chats/chat-1/quotations", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ json: quotationEntry().quotation });
  });

  await signInToChat(page, "provider");

  await page.getByRole("button", { name: "Enviar cotización" }).click();
  const dialog = page.getByRole("dialog", { name: "Envía tu cotización" });
  await dialog.getByLabel("Monto (CLP)").fill("125000");
  await dialog.getByLabel("Fecha del servicio").fill("2099-12-30T12:00");
  await dialog.getByLabel("Descripción").fill("Mudanza de dos ambientes");
  await expect(dialog.getByLabel("Vigencia (horas)")).toHaveValue("48");
  await dialog.getByRole("button", { name: "Enviar cotización" }).click();

  await expect(dialog).toBeHidden();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ amount: 125000, description: "Mudanza de dos ambientes", validityHours: 48 });
  expect(new Date(bodies[0].serviceAt as string).getTime()).toBe(new Date("2099-12-30T12:00").getTime());
});

test("provider sees a server rejection of the quotation as a readable message", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ viewerRole: "provider" }) }));
  await page.route("**/api/chats/chat-1/quotations", async (route) =>
    route.fulfill({ status: 403, json: { detail: "forbidden" } }),
  );

  await signInToChat(page, "provider");

  await page.getByRole("button", { name: "Enviar cotización" }).click();
  const dialog = page.getByRole("dialog", { name: "Envía tu cotización" });
  await dialog.getByLabel("Monto (CLP)").fill("125000");
  await dialog.getByLabel("Fecha del servicio").fill("2099-12-30T12:00");
  await dialog.getByLabel("Descripción").fill("Mudanza de dos ambientes");
  await dialog.getByRole("button", { name: "Enviar cotización" }).click();

  await expect(dialog.getByRole("alert")).toHaveText("Solo el prestador de esta conversación puede enviar cotizaciones.");
  await expect(dialog).toBeVisible();
});

test("customer sees a pending quotation with its amount, expiry and pay and reject actions", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ timeline: [quotationEntry()] }) }));

  await signInToChat(page, "customer");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await expect(quotation.getByText("Pendiente de pago")).toBeVisible();
  await expect(quotation.getByText("$125.000")).toBeVisible();
  await expect(quotation.getByText("Mudanza de dos ambientes")).toBeVisible();
  await expect(quotation.getByText("Vence")).toBeVisible();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toBeEnabled();
  await expect(quotation.getByRole("button", { name: "Rechazar" })).toBeEnabled();
});

test("customer rejects a quotation after confirming, and the card updates to rejected", async ({ page }) => {
  let rejected = false;
  const rejectCalls: string[] = [];
  await mockThread(page, async (route) =>
    route.fulfill({
      json: threadPage({
        timeline: [quotationEntry(rejected ? { status: "rejected" } : {})],
      }),
    }),
  );
  await page.route("**/api/quotations/quotation-1/reject", async (route) => {
    rejectCalls.push(route.request().method());
    rejected = true;
    await route.fulfill({ json: { quotationId: "quotation-1", status: "rejected" } });
  });

  await signInToChat(page, "customer");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await quotation.getByRole("button", { name: "Rechazar" }).click();
  await expect(quotation.getByText("¿Rechazar esta cotización? El prestador podrá enviarte otra.")).toBeVisible();
  await quotation.getByRole("button", { name: "Volver" }).click();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toBeVisible();

  await quotation.getByRole("button", { name: "Rechazar" }).click();
  await quotation.getByRole("button", { name: "Sí, rechazar" }).click();

  await expect(quotation.getByText("Rechazada")).toBeVisible();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toHaveCount(0);
  expect(rejectCalls).toEqual(["POST"]);
});

test("customer pay action opens the checkout URL returned by the payment request", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ timeline: [quotationEntry()] }) }));
  await page.route("**/api/quotations/quotation-1/payments", async (route) =>
    route.fulfill({ json: { paymentId: "payment-1", checkoutUrl: "https://checkout.example.test/session/1" } }),
  );
  await page.route("https://checkout.example.test/**", async (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Checkout de prueba</h1>" }),
  );

  await signInToChat(page, "customer");

  await page.getByRole("article", { name: "Cotización" }).getByRole("button", { name: "Pagar" }).click();

  await expect(page).toHaveURL("https://checkout.example.test/session/1");
});

test("a quotation that can no longer be paid explains it and refreshes the conversation", async ({ page }) => {
  await mockThread(page, async (route) => route.fulfill({ json: threadPage({ timeline: [quotationEntry()] }) }));
  await page.route("**/api/quotations/quotation-1/payments", async (route) =>
    route.fulfill({ status: 409, json: { detail: { type: "conflict", msg: "expired" } } }),
  );

  await signInToChat(page, "customer");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await quotation.getByRole("button", { name: "Pagar" }).click();

  await expect(quotation.getByRole("alert")).toHaveText("Esta cotización ya no se puede pagar. Actualizamos la conversación.");
});

test("paid quotation shows its payment date and offers no actions", async ({ page }) => {
  await mockThread(page, async (route) =>
    route.fulfill({
      json: threadPage({
        timeline: [quotationEntry({ status: "paid", paidAt: "2026-10-11T15:00:00Z" })],
      }),
    }),
  );

  await signInToChat(page, "customer");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await expect(quotation.getByText("Pagada", { exact: true })).toBeVisible();
  await expect(quotation.getByText("Pagada el")).toBeVisible();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toHaveCount(0);
  await expect(quotation.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
});

test("pending quotation past its expiry offers no actions to the customer", async ({ page }) => {
  await mockThread(page, async (route) =>
    route.fulfill({
      json: threadPage({
        timeline: [quotationEntry({ expiresAt: "2000-01-01T00:00:00Z" })],
      }),
    }),
  );

  await signInToChat(page, "customer");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await expect(quotation.getByText("Pendiente de pago")).toBeVisible();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toHaveCount(0);
  await expect(quotation.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
});

test("provider sees the quotation without customer actions", async ({ page }) => {
  await mockThread(page, async (route) =>
    route.fulfill({ json: threadPage({ viewerRole: "provider", timeline: [quotationEntry()] }) }),
  );

  await signInToChat(page, "provider");

  const quotation = page.getByRole("article", { name: "Cotización" });
  await expect(quotation.getByText("Pendiente de pago")).toBeVisible();
  await expect(quotation.getByRole("button", { name: "Pagar" })).toHaveCount(0);
  await expect(quotation.getByRole("button", { name: "Rechazar" })).toHaveCount(0);
});

test("conversation fits a phone-width viewport without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockThread(page, async (route) =>
    route.fulfill({
      json: threadPage({
        ...chatHeader({ counterpart: { name: "Ana Pérez con un nombre bastante largo para forzar el ajuste", kind: "customer", providerProfileId: null } }),
        timeline: [
          messageEntry(
            "message-1",
            "Mensaje largo sin espacios para verificar que el texto no empuje el ancho de la página más allá del viewport",
            false,
            "Ana Pérez",
          ),
          quotationEntry(),
        ],
      }),
    }),
  );

  await signInToChat(page, "customer");
  await expect(page.getByRole("list", { name: "Mensajes" }).getByRole("listitem")).toHaveCount(2);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
