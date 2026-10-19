import { expect, test, type Page } from "@playwright/test";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

async function mockPasswordLogin(page: Page, response: { status?: number; body: Record<string, unknown> }) {
  const tokenRequests: Array<Record<string, unknown>> = [];
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (url.pathname === "/auth/v1/token" && url.searchParams.get("grant_type") === "password") {
      tokenRequests.push(request.postDataJSON() as Record<string, unknown>);
      await route.fulfill({ status: response.status ?? 200, headers: corsHeaders, json: response.body });
      return;
    }
    await route.fulfill({ status: 200, headers: corsHeaders, json: {} });
  });
  return tokenRequests;
}

async function fillCredentials(page: Page, password: string) {
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill(password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
}

test("login page presents its welcome copy and the privacy notice in Spanish", async ({ page }) => {
  await page.goto("/login");
  await expect(page).toHaveTitle("Iniciar sesión | Amira");
  await expect(page.getByRole("heading", { level: 1, name: "El movimiento empieza con una cuenta segura." })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Qué bueno verte" })).toBeVisible();
  await expect(page.getByText("Ingresa para continuar donde quedaste.")).toBeVisible();
  await expect(page.getByText("CONECTA. COTIZA. COORDINA.")).toBeVisible();
  await expect(page.getByText("Amira nunca solicita códigos SMS por teléfono o mensaje directo.")).toBeVisible();
});

test("login page links back to the landing page and to registration", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("link", { name: "Amira, volver al inicio" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Regístrate" })).toHaveAttribute("href", "/registro");
  await page.getByRole("link", { name: "Regístrate" }).click();
  await expect(page).toHaveURL(/\/registro$/);
  await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible();
});

test("login form shows only email and password fields and the submit action", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Correo electrónico")).toBeVisible();
  await expect(page.locator("#auth-password")).toHaveAttribute("autocomplete", "current-password");
  await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeEnabled();
  await expect(page.getByLabel("Nombre")).toHaveCount(0);
  await expect(page.getByLabel("Teléfono móvil")).toHaveCount(0);
  await expect(page.getByLabel("RUT personal")).toHaveCount(0);
  await expect(page.getByLabel("Confirmar contraseña")).toHaveCount(0);
});

test("password reveal toggles the field between hidden and visible text", async ({ page }) => {
  await page.goto("/login");
  const password = page.locator("#auth-password");
  await password.fill("clave-visible");
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Mostrar contraseña" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue("clave-visible");
  await page.getByRole("button", { name: "Ocultar contraseña" }).click();
  await expect(password).toHaveAttribute("type", "password");
});

test("empty login submit is stopped by native validation before any token request", async ({ page }) => {
  const tokenRequests = await mockPasswordLogin(page, { body: {} });
  await page.goto("/login");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByLabel("Correo electrónico")).toBeFocused();
  await expect(page.getByLabel("Correo electrónico")).toHaveJSProperty("validity.valueMissing", true);
  await expect(page.getByRole("heading", { name: "Qué bueno verte" })).toBeVisible();
  expect(tokenRequests).toHaveLength(0);
});

test("rate-limited login shows an actionable retry message", async ({ page }) => {
  await mockPasswordLogin(page, { status: 429, body: { code: "over_request_rate_limit", msg: "Too many requests" } });
  await page.goto("/login");
  await fillCredentials(page, "un-password-seguro");
  await expect(page.locator(".auth-error")).toContainText("Hubo demasiados intentos. Espera un momento antes de volver a probar.");
  await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeEnabled();
});

test("login with an unconfirmed email explains that the address must be confirmed first", async ({ page }) => {
  await mockPasswordLogin(page, { status: 400, body: { code: "email_not_confirmed", msg: "Email not confirmed" } });
  await page.goto("/login");
  await fillCredentials(page, "un-password-seguro");
  await expect(page.locator(".auth-error")).toContainText("Confirma tu correo antes de iniciar sesión.");
  await expect(page.locator(".auth-error")).toContainText("Revisa también la carpeta de correo no deseado.");
  await expect(page.getByRole("heading", { name: "Qué bueno verte" })).toBeVisible();
});

test("unexpected auth server failure shows the generic retry message and keeps the typed email", async ({ page }) => {
  await mockPasswordLogin(page, { status: 500, body: { msg: "internal boom" } });
  await page.goto("/login");
  await fillCredentials(page, "un-password-seguro");
  await expect(page.locator(".auth-error")).toHaveText("No pudimos completar la operación. Revisa los datos e intenta nuevamente.");
  await expect(page.getByLabel("Correo electrónico")).toHaveValue("persona@example.test");
});

test("login layout fits a 320px phone without horizontal overflow and keeps the form reachable", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeVisible();
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
