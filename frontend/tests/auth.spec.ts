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

async function installAuthMocks(page: Page, options: { accountExists?: boolean; refresh?: boolean; existingPhone?: boolean } = {}) {
  const events: Array<{ path: string; method: string; body?: Record<string, unknown>; authorization?: string }> = [];
  let factorExists = options.existingPhone ?? false;
  let factorPhone = factorExists ? "+56912345678" : "";
  let challengeNumber = 0;
  let failedVerification = false;
  let signupRedirect = "";
  let provisioned = options.accountExists ?? false;

  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();
    let body: Record<string, unknown> | undefined;
    try { body = request.postDataJSON() as Record<string, unknown>; } catch { /* GET or empty body */ }
    events.push({ path, method, body });

    if (path === "/signup" && method === "POST") {
      signupRedirect = url.searchParams.get("redirect_to") ?? String((body?.options as { email_redirect_to?: string } | undefined)?.email_redirect_to ?? "");
      await route.fulfill({ json: { user: { ...user, email_confirmed_at: null, confirmed_at: null }, session: null } });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      if (body?.password === "incorrect password") {
        await route.fulfill({ status: 400, json: { code: "invalid_credentials", msg: "Invalid login credentials" } });
        return;
      }
      await route.fulfill({ json: session("aal1", "password-aal1-token", 3600) });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "refresh_token") {
      await route.fulfill({ json: session(options.refresh ? "aal2" : "aal1", options.refresh ? "refreshed-aal2-token" : "refreshed-aal1-token", 3600) });
      return;
    }
    if (path === "/user" && method === "GET") {
      const factors = factorExists ? [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: factorPhone }] : [];
      await route.fulfill({ json: { ...user, factors } });
      return;
    }
    if (path === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: factorExists ? [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: factorPhone }] : [], phone: factorExists ? [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: factorPhone }] : [], totp: [] } });
      return;
    }
    if (path === "/factors" && method === "POST") {
      factorExists = true;
      factorPhone = String(body?.phone ?? "");
      await route.fulfill({ json: { id: "factor-sms-1", factor_type: "phone", status: "unverified", phone: factorPhone, friendly_name: "Amira SMS" } });
      return;
    }
    if (path === "/factors/factor-sms-1/challenge" && method === "POST") {
      challengeNumber += 1;
      await route.fulfill({ json: { id: `challenge-${challengeNumber}`, expires_at: Date.now() + 300000 } });
      return;
    }
    if (path === "/factors/factor-sms-1/verify" && method === "POST") {
      if (body?.code === "111111" && !failedVerification) {
        failedVerification = true;
        await route.fulfill({ status: 400, json: { code: "mfa_verification_failed", msg: "Invalid verification code" } });
        return;
      }
      await route.fulfill({ json: session("aal2", "verified-aal2-token", options.refresh ? 1 : 3600) });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await page.route("**/api/account/me", async (route) => {
    events.push({ path: "/api/account/me", method: "GET", authorization: route.request().headers()["authorization"] });
    if (provisioned) await route.fulfill({ json: { user_id: "account-test-1", role: "client", profile_id: null } });
    else await route.fulfill({ status: 404, json: { detail: "Account is not provisioned." } });
  });
  await page.route("**/api/account/provision", async (route) => {
    const request = route.request();
    const body = request.postDataJSON() as Record<string, unknown>;
    events.push({ path: "/api/account/provision", method: "POST", body, authorization: request.headers()["authorization"] });
    if (options.refresh && request.headers()["authorization"] !== `Bearer ${accessToken("aal2", "refreshed-aal2-token")}`) {
      await route.fulfill({ status: 401, json: { detail: "Expected refreshed verification token." } });
      return;
    }
    if (body.role === "independent_driver") {
      await route.fulfill({ status: 503, json: { detail: "Independent driver provisioning is not configured." } });
      return;
    }
    provisioned = true;
    await route.fulfill({ status: 201, json: { user_id: "account-test-1", role: body.role, profile_id: body.role === "client" ? null : "profile-test-1" } });
  });

  return { events, getSignupRedirect: () => signupRedirect };
}

test("registration waits for email confirmation before asking for account details", async ({ page }) => {
  const mocks = await installAuthMocks(page);
  await page.goto("/registro");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page.getByRole("heading", { name: "Confirma tu correo" })).toBeVisible();
  await expect(page.getByText(/Después podrás completar tu cuenta/)).toBeVisible();
  await expect.poll(() => new URL(mocks.getSignupRedirect()).pathname).toBe("/auth/callback");
  expect(new URL(mocks.getSignupRedirect()).searchParams.get("next")).toBe("/registro?step=account");
  expect(mocks.events.some((event) => event.path === "/api/account/provision")).toBe(false);
});

test("login rejects invalid credentials without leaving the password form", async ({ page }) => {
  await installAuthMocks(page);
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("incorrect password");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.locator(".auth-error")).toContainText("El correo o la contraseña no son correctos");
  await expect(page.locator("#auth-password")).toHaveValue("incorrect password");
  await expect(page.locator("#auth-password")).toHaveAttribute("type", "password");
});

test("login requires SMS, retries a rejected challenge, and provisions only after AAL2", async ({ page }) => {
  const mocks = await installAuthMocks(page, { refresh: true });
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.getByRole("heading", { name: "Verifica tu teléfono" })).toBeVisible();
  await page.getByLabel("Número de teléfono móvil").fill("+56912345678");
  await page.getByRole("button", { name: "Enviar código SMS" }).click();
  await expect(page.getByRole("heading", { name: "Ingresa tu código SMS" })).toBeVisible();
  await expect(page.getByLabel("Código de verificación")).toBeFocused();

  await page.getByLabel("Código de verificación").fill("111111");
  await page.getByRole("button", { name: "Verificar teléfono" }).click();
  await expect(page.locator(".auth-error")).toContainText("El código no es válido o venció");
  await page.getByRole("button", { name: "Enviar otro código" }).click();
  await page.getByLabel("Código de verificación").fill("246810");
  await page.getByRole("button", { name: "Verificar teléfono" }).click();
  await expect(page.getByLabel("¿Cómo usarás Amira?")).toBeVisible();
  await page.getByLabel("Nombre").fill("Camila");
  await page.getByLabel("Apellido").fill("Rojas");
  await page.getByRole("button", { name: "Completar registro" }).click();
  await expect(page).toHaveURL(/\/servicios$/);
  const provisionRequest = mocks.events.find((event) => event.path === "/api/account/provision");
  expect(provisionRequest?.authorization).toBe(`Bearer ${accessToken("aal2", "refreshed-aal2-token")}`);
  expect(provisionRequest?.body).toEqual({ role: "client", first_name: "Camila", last_name: "Rojas" });
  expect(mocks.events.some((event) => event.method === "POST" && event.path === "/factors" && event.body?.phone === "+56912345678")).toBe(true);
  expect(mocks.events.filter((event) => event.path === "/factors/factor-sms-1/challenge")).toHaveLength(2);
});

test("confirmed registration supports company fields and surfaces unavailable driver provisioning", async ({ page }) => {
  const mocks = await installAuthMocks(page, { existingPhone: true });
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByRole("heading", { name: "Ingresa tu código SMS" })).toBeVisible();
  await page.getByLabel("Código de verificación").fill("246810");
  await page.getByRole("button", { name: "Verificar teléfono" }).click();
  await expect(page.getByLabel("Nombre")).toBeVisible();
  await page.getByLabel("¿Cómo usarás Amira?").selectOption("company_owner");
  await page.locator("#auth-first-name").fill("Ana");
  await page.getByLabel("Apellido").fill("Pérez");
  await page.getByLabel("Nombre público del prestador").fill("Transportes Sur");
  await page.getByLabel("RUT de la empresa").fill("76.123.456-7");
  await page.getByRole("button", { name: "Completar registro" }).click();
  await expect(page).toHaveURL(/\/servicios$/);
  const company = mocks.events.find((event) => event.path === "/api/account/provision");
  expect(company?.body).toEqual({ role: "company_owner", first_name: "Ana", last_name: "Pérez", display_name: "Transportes Sur", company_tax_id: "76.123.456-7" });
});

test("independent-driver provisioning failure gives an actionable message", async ({ page }) => {
  await installAuthMocks(page, { existingPhone: true });
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByLabel("Código de verificación")).toBeVisible();
  await page.getByLabel("Código de verificación").fill("246810");
  await page.getByRole("button", { name: "Verificar teléfono" }).click();
  await expect(page.getByLabel("¿Cómo usarás Amira?")).toBeVisible();
  await page.getByLabel("¿Cómo usarás Amira?").selectOption("independent_driver");
  await page.locator("#auth-first-name").fill("Pedro");
  await page.getByLabel("Apellido").fill("Soto");
  await page.getByLabel("Nombre público del prestador").fill("Fletes Pedro");
  await page.getByRole("button", { name: "Completar registro" }).click();
  await expect(page.locator(".auth-error")).toContainText("todavía requiere configuración");
  await expect(page.getByLabel("Nombre público del prestador")).toHaveValue("Fletes Pedro");
});

test("callback rejects external next destinations and returns to the login flow", async ({ page }) => {
  await page.goto("/auth/callback?error=access_denied&next=https%3A%2F%2Fevil.test%2Fsteal");
  await expect(page).toHaveURL(/\/login\?message=confirmation$/);
  await expect(page.getByRole("heading", { name: "Qué bueno verte" })).toBeVisible();
});

test("confirmed callback persists a verified session through the account redirect", async ({ page }) => {
  const mocks = await installAuthMocks(page);
  await page.goto("/registro");
  await page.getByLabel("Correo electrónico").fill("confirmed@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Confirma tu correo" })).toBeVisible();
  const callback = await page.request.get("/auth/callback?code=valid-confirmation-code&next=%2Fregistro%3Fstep%3Daccount", { maxRedirects: 0 });
  expect(callback.status()).toBe(307);
  expect(callback.headers().location).toMatch(/\/registro\?step=account$/);
  const sessionCookies = (await page.context().cookies()).filter((cookie) => cookie.name.endsWith("auth-token"));
  expect(sessionCookies.length).toBeGreaterThan(0);
  expect(mocks.events.some((event) => event.path === "/signup")).toBe(true);
});

test("confirmed callback rejects an external next destination", async ({ page }) => {
  await installAuthMocks(page);
  await page.goto("/registro");
  await page.getByLabel("Correo electrónico").fill("confirmed@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Confirma tu correo" })).toBeVisible();
  const callback = await page.request.get("/auth/callback?code=valid-confirmation-code&next=https%3A%2F%2Fevil.test%2Fcollect", { maxRedirects: 0 });
  expect(callback.status()).toBe(307);
  expect(callback.headers().location).toMatch(/\/servicios$/);
});

test("successful login sends an external next destination to the safe marketplace default", async ({ page }) => {
  await installAuthMocks(page, { existingPhone: true, accountExists: true });
  await page.goto("/login?next=https%3A%2F%2Fevil.test%2Fcollect");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByLabel("Código de verificación")).toBeVisible();
  await page.getByLabel("Código de verificación").fill("246810");
  await page.getByRole("button", { name: "Verificar teléfono" }).click();
  await expect(page).toHaveURL(/\/servicios$/);
});

test("home and desktop/mobile marketplace navigation expose real auth routes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");

  await page.goto("/servicios");
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  const mobileNav = page.getByRole("navigation", { name: "Navegación móvil" });
  await expect(mobileNav.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  await expect(mobileNav.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");
  await mobileNav.getByRole("link", { name: "Iniciar sesión" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("auth layout remains usable at a narrow mobile viewport", async ({ page }) => {
  await installAuthMocks(page);
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/registro");
  await expect(page.getByLabel("Correo electrónico")).toBeVisible();
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
