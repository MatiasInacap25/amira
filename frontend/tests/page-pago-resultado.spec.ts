import { expect, test, type Page } from "@playwright/test";

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

const resultPath = "/pagos/resultado?paymentId=payment-1&status=approved";
const statusPath = "**/api/payments/payment-1";

const paidPayment = { paymentId: "payment-1", status: "approved", quotationId: "quotation-1", quotationStatus: "paid", chatId: "chat-1" };
const pendingPayment = { paymentId: "payment-1", status: "pending", quotationId: "quotation-1", quotationStatus: "pending", chatId: "chat-1" };
const rejectedPayment = { paymentId: "payment-1", status: "rejected", quotationId: "quotation-1", quotationStatus: "pending", chatId: "chat-1" };

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

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-pago-simulado.spec.ts.
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
}

// Signs in through the real login form and lands on the result page, so the browser holds a session.
async function signInToResult(page: Page, next = resultPath) {
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "customer", profile_id: null } }),
  );
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.waitForURL((url) => url.pathname === "/pagos/resultado");
}

test("link without a payment id says the payment cannot be found, with a way back to messages", async ({ page }) => {
  await page.goto("/pagos/resultado");

  const main = page.getByRole("main");
  await expect(main.getByRole("status").getByRole("heading", { level: 1, name: "No encontramos este pago" })).toBeVisible();
  await expect(main.getByText("El enlace no tiene la información del pago.")).toBeVisible();
  await expect(main.getByRole("link", { name: "Ver mis mensajes" })).toHaveAttribute("href", "/mensajes");
});

test("approved payment shows the confirmed result and links back to the conversation", async ({ page }) => {
  await signInToResult(page);
  await page.route(statusPath, async (route) => route.fulfill({ json: paidPayment }));
  await page.goto(resultPath);

  const main = page.getByRole("main");
  await expect(main.getByRole("status").getByRole("heading", { level: 1, name: "Pago recibido" })).toBeVisible();
  await expect(main.getByText("Tu servicio quedó confirmado. Puedes seguir la coordinación desde la conversación.")).toBeVisible();
  await expect(main.getByRole("link", { name: "Volver a la conversación" })).toHaveAttribute("href", "/mensajes/chat-1");
});

test("rejected payment shows the failure as an alert with a way back to the conversation", async ({ page }) => {
  await signInToResult(page);
  await page.route(statusPath, async (route) => route.fulfill({ json: rejectedPayment }));
  await page.goto("/pagos/resultado?paymentId=payment-1&status=rejected");

  const main = page.getByRole("main");
  const alert = main.getByRole("alert");
  await expect(alert.getByRole("heading", { level: 1, name: "El pago no se completó" })).toBeVisible();
  await expect(alert.getByText("La cotización no quedó pagada. Si todavía está vigente, puedes intentarlo nuevamente desde la conversación.")).toBeVisible();
  await expect(alert.getByRole("link", { name: "Volver a la conversación" })).toHaveAttribute("href", "/mensajes/chat-1");
});

test("pending payment keeps polling and switches to the confirmed result when the provider confirms", async ({ page }) => {
  await signInToResult(page);

  // Dev can send the first read twice, so the provider flips on an explicit flag rather than a read count.
  let confirmed = false;
  let reads = 0;
  await page.route(statusPath, async (route) => {
    reads += 1;
    await route.fulfill({ json: confirmed ? paidPayment : pendingPayment });
  });
  await page.goto(resultPath);

  const main = page.getByRole("main");
  await expect(main.getByRole("status").getByRole("heading", { level: 1, name: "Estamos confirmando tu pago" })).toBeVisible();
  await expect(main.getByRole("status")).toHaveAttribute("aria-live", "polite");

  const readsWhilePending = reads;
  confirmed = true;
  await expect(main.getByRole("status").getByRole("heading", { level: 1, name: "Pago recibido" })).toBeVisible({ timeout: 15_000 });
  expect(reads).toBeGreaterThan(readsWhilePending);
});

test("a payment that no longer exists says so and offers no retry", async ({ page }) => {
  await signInToResult(page);
  await page.route(statusPath, async (route) => route.fulfill({ status: 404, json: { detail: "Payment not found" } }));
  await page.goto(resultPath);

  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert.getByRole("heading", { level: 1, name: "No encontramos este pago" })).toBeVisible();
  await expect(alert.getByText("Es posible que el enlace sea incorrecto o que no tengas acceso a este pago.")).toBeVisible();
  await expect(alert.getByRole("button", { name: "Reintentar" })).toHaveCount(0);
  await expect(alert.getByRole("link", { name: "Ver mis mensajes" })).toHaveAttribute("href", "/mensajes");
});

test("a failed status read offers a retry that shows the result once the read succeeds", async ({ page }) => {
  await signInToResult(page);

  // Reads fail until the test asks for a retry; a count would race the duplicate first load in dev.
  let recovered = false;
  await page.route(statusPath, async (route) => {
    if (!recovered) {
      await route.fulfill({ status: 500, json: { detail: "boom" } });
      return;
    }
    await route.fulfill({ json: paidPayment });
  });
  await page.goto(resultPath);

  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert.getByRole("heading", { level: 1, name: "No pudimos consultar tu pago" })).toBeVisible();
  await expect(alert.getByText("Revisa tu conexión e inténtalo nuevamente.")).toBeVisible();
  recovered = true;
  await alert.getByRole("button", { name: "Reintentar" }).click();

  await expect(page.getByRole("main").getByRole("heading", { level: 1, name: "Pago recibido" })).toBeVisible();
});

test("a visitor without a session never requests the payment and is asked to sign in", async ({ page }) => {
  let reads = 0;
  await page.route(statusPath, async (route) => {
    reads += 1;
    await route.fulfill({ json: paidPayment });
  });

  await page.goto(resultPath);

  const main = page.getByRole("main");
  const alert = main.getByRole("alert");
  await expect(alert).toHaveText("Inicia sesión con tu correo confirmado para ver tu pago.");
  await expect(main.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
    "href",
    `/login?next=${encodeURIComponent(resultPath)}`,
  );
  await expect(main.getByRole("heading", { level: 1, name: "Consultando tu pago…" })).toHaveCount(0);
  await page.waitForTimeout(1000);
  expect(reads).toBe(0);
});

test("result fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await signInToResult(page);
  await page.route(statusPath, async (route) => route.fulfill({ json: paidPayment }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(resultPath);

  await expect(page.getByRole("main").getByRole("heading", { level: 1, name: "Pago recibido" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("link", { name: "Volver a la conversación" })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
