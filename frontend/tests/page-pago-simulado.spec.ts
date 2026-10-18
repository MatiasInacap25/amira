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

const checkoutPath = "/pagos/simulado?paymentId=payment-1&token=checkout-token-1";
const completionPath = "**/api/payments/simulated/payment-1/complete";

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

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-chat.spec.ts.
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

// Signs in through the real login form and lands on the checkout page, so the browser holds a session.
async function signInToCheckout(page: Page) {
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "customer", profile_id: null } }),
  );
  await page.goto(`/login?next=${encodeURIComponent(checkoutPath)}`);
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.waitForURL((url) => url.pathname === "/pagos/simulado");
}

test("link without a payment or token asks the visitor to start the payment again", async ({ page }) => {
  await page.goto("/pagos/simulado");

  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert.getByRole("heading", { name: "Enlace de pago incompleto" })).toBeVisible();
  await expect(alert.getByText("Vuelve a la conversación e inicia el pago nuevamente.")).toBeVisible();
  await expect(alert.getByRole("link", { name: "Ver mis mensajes" })).toHaveAttribute("href", "/mensajes");
});

test("link that carries a payment but no token is treated as incomplete", async ({ page }) => {
  await page.goto("/pagos/simulado?paymentId=payment-1");

  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert.getByRole("heading", { name: "Enlace de pago incompleto" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aprobar pago" })).toHaveCount(0);
});

test("checkout shows the test-payment notice and both decisions", async ({ page }) => {
  await page.goto(checkoutPath);

  const main = page.getByRole("main");
  await expect(main.getByText("PAGO DE PRUEBA")).toBeVisible();
  await expect(main.getByRole("heading", { level: 1, name: "Pago simulado" })).toBeVisible();
  await expect(main.getByText("Este entorno de desarrollo no cobra dinero real. Elige el resultado que quieres probar.")).toBeVisible();
  await expect(main.getByRole("button", { name: "Aprobar pago" })).toBeEnabled();
  await expect(main.getByRole("button", { name: "Rechazar pago" })).toBeEnabled();
  await expect(main.getByText("Enlace de pago incompleto")).toHaveCount(0);
});

test("approving sends the checkout token with the signed-in session and opens the approved result", async ({ page }) => {
  await signInToCheckout(page);

  let body: unknown;
  let authorization = "";
  await page.route(completionPath, async (route) => {
    body = route.request().postDataJSON();
    authorization = route.request().headers()["authorization"] ?? "";
    await route.fulfill({ json: { paymentId: "payment-1", status: "approved" } });
  });

  await page.getByRole("button", { name: "Aprobar pago" }).click();
  await page.waitForURL((url) => url.pathname === "/pagos/resultado" && url.searchParams.get("status") === "approved");

  const landed = new URL(page.url());
  expect(landed.searchParams.get("paymentId")).toBe("payment-1");
  expect(body).toEqual({ token: "checkout-token-1", approve: true });
  expect(authorization).toMatch(/^Bearer .*verified-aal2-token$/);
});

test("rejecting sends the decline and opens the rejected result", async ({ page }) => {
  await signInToCheckout(page);

  let body: unknown;
  await page.route(completionPath, async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { paymentId: "payment-1", status: "rejected" } });
  });

  await page.getByRole("button", { name: "Rechazar pago" }).click();
  await page.waitForURL((url) => url.pathname === "/pagos/resultado" && url.searchParams.get("status") === "rejected");

  expect(new URL(page.url()).searchParams.get("paymentId")).toBe("payment-1");
  expect(body).toEqual({ token: "checkout-token-1", approve: false });
});

test("both decisions stay disabled while the approval is pending", async ({ page }) => {
  await signInToCheckout(page);

  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(completionPath, async (route) => {
    await gate;
    await route.fulfill({ json: { paymentId: "payment-1", status: "approved" } });
  });

  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Aprobar pago" }).click();

  await expect(main.getByRole("button", { name: "Aprobando…" })).toBeDisabled();
  await expect(main.getByRole("button", { name: "Rechazar pago" })).toBeDisabled();

  release();
  await page.waitForURL((url) => url.pathname === "/pagos/resultado");
});

test("a checkout that no longer exists explains it and keeps the page on the decision", async ({ page }) => {
  await signInToCheckout(page);

  await page.route(completionPath, async (route) => {
    await route.fulfill({ status: 404, json: { detail: "Payment checkout not found" } });
  });

  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Aprobar pago" }).click();

  await expect(main.getByRole("alert")).toHaveText("Este pago simulado ya no está disponible.");
  await expect(main.getByRole("button", { name: "Aprobar pago" })).toBeEnabled();
  await expect(main.getByRole("button", { name: "Rechazar pago" })).toBeEnabled();
  expect(new URL(page.url()).pathname).toBe("/pagos/simulado");
});

test("a failed decision shows the retry message and re-enables both buttons", async ({ page }) => {
  await signInToCheckout(page);

  await page.route(completionPath, async (route) => {
    await route.fulfill({ status: 500, json: { detail: "boom" } });
  });

  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Rechazar pago" }).click();

  await expect(main.getByRole("alert")).toHaveText("No pudimos registrar tu decisión. Inténtalo nuevamente.");
  await expect(main.getByRole("button", { name: "Aprobar pago" })).toBeEnabled();
  await expect(main.getByRole("button", { name: "Rechazar pago" })).toBeEnabled();
  expect(new URL(page.url()).pathname).toBe("/pagos/simulado");
});

test("a visitor without a confirmed session sends no decision and is asked to sign in", async ({ page }) => {
  let completions = 0;
  await page.route(completionPath, async (route) => {
    completions += 1;
    await route.fulfill({ status: 401, json: { detail: "unauthorized" } });
  });

  await page.goto(checkoutPath);
  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Aprobar pago" }).click();

  const alert = main.getByRole("alert");
  await expect(alert).toHaveText("Inicia sesión con tu correo confirmado para ver tu pago.");
  await expect(main.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
    "href",
    `/login?next=${encodeURIComponent(checkoutPath)}`,
  );
  expect(completions).toBe(0);
  expect(new URL(page.url()).pathname).toBe("/pagos/simulado");
});

test("checkout fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(checkoutPath);

  const main = page.getByRole("main");
  await expect(main.getByRole("button", { name: "Aprobar pago" })).toBeVisible();
  await expect(main.getByRole("button", { name: "Rechazar pago" })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
