import { expect, test, type Page } from "@playwright/test";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

const validPassword = "un-password-seguro";

async function mockSignup(page: Page) {
  const signupRequests: Array<Record<string, unknown>> = [];
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (url.pathname === "/auth/v1/signup" && request.method() === "POST") {
      signupRequests.push(request.postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        headers: corsHeaders,
        json: {
          user: {
            id: "user-test-2",
            aud: "authenticated",
            role: "authenticated",
            email: "persona@example.test",
            email_confirmed_at: null,
            app_metadata: { provider: "email", providers: ["email"] },
            user_metadata: {},
            created_at: "2026-10-01T11:00:00.000Z",
          },
          session: null,
        },
      });
      return;
    }
    await route.fulfill({ status: 200, headers: corsHeaders, json: {} });
  });
  return signupRequests;
}

async function fillRegistrationForm(
  page: Page,
  overrides: { phone?: string; nationalId?: string; password?: string; passwordConfirm?: string } = {},
) {
  await page.locator("#auth-first-name").fill("Camila");
  await page.locator("#auth-last-name").fill("Rojas");
  await page.locator("#auth-phone").fill(overrides.phone ?? "+56912345678");
  await page.locator("#auth-national-id").fill(overrides.nationalId ?? "12.345.678-5");
  await page.locator("#auth-birth-date").fill("1990-01-01");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill(overrides.password ?? validPassword);
  await page.locator("#auth-password-confirm").fill(overrides.passwordConfirm ?? validPassword);
}

test("registration page presents its title and Spanish copy", async ({ page }) => {
  await page.goto("/registro");
  await expect(page).toHaveTitle("Crear cuenta | Amira");
  await expect(page.getByRole("heading", { level: 1, name: "El movimiento empieza con una cuenta segura." })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Crea tu cuenta" })).toBeVisible();
  await expect(page.getByText("Regístrate con tu correo y confirma la dirección antes de completar tu perfil.")).toBeVisible();
  await expect(page.getByText("CONECTA. COTIZA. COORDINA.")).toBeVisible();
});

test("registration page links back to the landing page", async ({ page }) => {
  await page.goto("/registro");
  await expect(page.getByRole("link", { name: "Amira, volver al inicio" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/");
});

test("registration switch link opens the login form", async ({ page }) => {
  await page.goto("/registro");
  await expect(page.getByText("¿Ya tienes una cuenta?")).toBeVisible();
  await page.getByRole("link", { name: "Inicia sesión" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Qué bueno verte" })).toBeVisible();
});

test("customer registration shows the identity fields and hides the provider role choice", async ({ page }) => {
  await page.goto("/registro");
  await expect(page.getByLabel("Nombre")).toBeVisible();
  await expect(page.getByLabel("Apellido")).toBeVisible();
  await expect(page.getByLabel("Teléfono móvil")).toBeVisible();
  await expect(page.getByLabel("RUT personal")).toBeVisible();
  await expect(page.getByLabel("Fecha de nacimiento")).toBeVisible();
  await expect(page.getByLabel("Contraseña", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Confirmar contraseña")).toBeVisible();
  await expect(page.getByLabel("Quiero ofrecer mis servicios como")).toHaveCount(0);
  await expect(page.getByLabel("RUT de la empresa")).toHaveCount(0);
});

test("registration fields expose autocomplete hints for password managers and phone keyboards", async ({ page }) => {
  await page.goto("/registro");
  await expect(page.getByLabel("Correo electrónico")).toHaveAttribute("autocomplete", "email");
  await expect(page.locator("#auth-password")).toHaveAttribute("autocomplete", "new-password");
  await expect(page.locator("#auth-password-confirm")).toHaveAttribute("autocomplete", "new-password");
  await expect(page.locator("#auth-phone")).toHaveAttribute("inputmode", "tel");
  await expect(page.locator("#auth-national-id")).toHaveAttribute("autocomplete", "off");
});

test("RUT is reformatted with dots and check digit when the field loses focus", async ({ page }) => {
  await page.goto("/registro");
  await page.locator("#auth-national-id").fill("123456785");
  await page.locator("#auth-national-id").press("Tab");
  await expect(page.locator("#auth-national-id")).toHaveValue("12.345.678-5");
});

test("password reveal toggles both password fields together", async ({ page }) => {
  await page.goto("/registro");
  const password = page.locator("#auth-password");
  const confirmation = page.locator("#auth-password-confirm");
  await password.fill("clave-visible");
  await confirmation.fill("clave-visible");
  await expect(password).toHaveAttribute("type", "password");
  await expect(confirmation).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Mostrar contraseña" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(confirmation).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Ocultar contraseña" }).click();
  await expect(password).toHaveAttribute("type", "password");
  await expect(confirmation).toHaveAttribute("type", "password");
});

test("empty registration submit is stopped by native validation before any signup request", async ({ page }) => {
  const signupRequests = await mockSignup(page);
  await page.goto("/registro");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#auth-first-name")).toBeFocused();
  await expect(page.locator("#auth-first-name")).toHaveJSProperty("validity.valueMissing", true);
  await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible();
  expect(signupRequests).toHaveLength(0);
});

test("password shorter than eight characters is stopped by native validation", async ({ page }) => {
  const signupRequests = await mockSignup(page);
  await page.goto("/registro");
  await fillRegistrationForm(page, { password: "corta", passwordConfirm: "corta" });
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#auth-password")).toHaveJSProperty("validity.tooShort", true);
  await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible();
  expect(signupRequests).toHaveLength(0);
});

test("mismatched password confirmation shows an alert and sends no signup request", async ({ page }) => {
  const signupRequests = await mockSignup(page);
  await page.goto("/registro");
  await fillRegistrationForm(page, { passwordConfirm: "otra-clave-distinta" });
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator(".auth-error")).toContainText("Las contraseñas no coinciden.");
  await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible();
  expect(signupRequests).toHaveLength(0);
});

test("phone number with spaces and separators passes validation and reaches signup", async ({ page }) => {
  const signupRequests = await mockSignup(page);
  await page.goto("/registro");
  await fillRegistrationForm(page, { phone: "+56 9 1234 5678" });
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Confirma tu correo" })).toBeVisible();
  expect(signupRequests).toHaveLength(1);
  expect(signupRequests[0]?.email).toBe("persona@example.test");
});

test("corrected RUT clears its inline error on the next submit and lets signup proceed", async ({ page }) => {
  const signupRequests = await mockSignup(page);
  await page.goto("/registro");
  await fillRegistrationForm(page, { nationalId: "12.345.678-6" });
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#auth-national-id-error")).toContainText("El RUT no es válido. Revisa el dígito verificador.");
  expect(signupRequests).toHaveLength(0);

  await page.locator("#auth-national-id").fill("12.345.678-5");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Confirma tu correo" })).toBeVisible();
  await expect(page.locator("#auth-national-id-error")).toHaveCount(0);
  expect(signupRequests).toHaveLength(1);
});
