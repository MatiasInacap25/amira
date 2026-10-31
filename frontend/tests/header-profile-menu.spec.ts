import { expect, test, type Page } from "@playwright/test";
import { locationsResponse } from "./support/catalog-fixtures";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

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

function accessToken(id = "header-access-token") {
  const payload = Buffer.from(JSON.stringify({ aal: "aal1", exp: 2000000000, sub: user.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.${id}`;
}

function session() {
  return {
    access_token: accessToken(),
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: "refresh-test-token",
    user,
  };
}

// Fake Supabase Auth plus the header's account and chat calls. Signing out records a POST /logout.
async function installHeaderMocks(page: Page) {
  const events: Array<{ path: string; method: string }> = [];

  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();
    events.push({ path, method });

    if (method === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ headers: corsHeaders, json: session() });
      return;
    }
    if (path === "/user" && method === "GET") {
      await route.fulfill({ headers: corsHeaders, json: { ...user, factors: [] } });
      return;
    }
    if (path === "/logout" && method === "POST") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    await route.fulfill({ status: 404, headers: corsHeaders, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await page.route("**/api/locations", async (route) => route.fulfill({ json: locationsResponse }));
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role: "client", profile_id: null } }));
  await page.route("**/api/chats/unread", async (route) => route.fulfill({ json: { total: 0 } }));

  return events;
}

// Signs in through the real login form so the Supabase client stores the session the header reads.
async function signIn(page: Page) {
  const tokenRequest = page.waitForRequest((request) => request.url().includes("/auth/v1/token") && request.method() === "POST");
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await tokenRequest;
}

const header = (page: Page) => page.locator("header.site-header");

test("anonymous header shows the sign-in and registration links and no profile menu", async ({ page }) => {
  await installHeaderMocks(page);
  await page.goto("/");

  await expect(header(page).getByRole("link", { name: "Iniciar sesión" })).toBeVisible();
  await expect(header(page).getByRole("link", { name: "Crear cuenta" })).toBeVisible();
  await expect(header(page).getByRole("button", { name: "Menú de perfil" })).toHaveCount(0);
});

test("signed-in header hides the auth links and shows the profile menu button", async ({ page }) => {
  await installHeaderMocks(page);
  await signIn(page);
  await page.goto("/");

  await expect(header(page).getByRole("button", { name: "Menú de perfil" })).toBeVisible();
  await expect(header(page).getByRole("link", { name: "Iniciar sesión" })).toHaveCount(0);
  await expect(header(page).getByRole("link", { name: "Crear cuenta" })).toHaveCount(0);
});

test("profile menu opens with the settings link and the sign-out action", async ({ page }) => {
  await installHeaderMocks(page);
  await signIn(page);
  await page.goto("/");

  const toggle = header(page).getByRole("button", { name: "Menú de perfil" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");

  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitem", { name: "Configuración del perfil" })).toHaveAttribute("href", "/cuenta/perfil");
  await expect(menu.getByRole("menuitem", { name: "Cerrar sesión" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
});

test("signing out from the profile menu restores the anonymous auth links", async ({ page }) => {
  const events = await installHeaderMocks(page);
  await signIn(page);
  await page.goto("/");

  await header(page).getByRole("button", { name: "Menú de perfil" }).click();
  await page.getByRole("menu").getByRole("menuitem", { name: "Cerrar sesión" }).click();

  await expect(header(page).getByRole("link", { name: "Iniciar sesión" })).toBeVisible();
  await expect(header(page).getByRole("link", { name: "Crear cuenta" })).toBeVisible();
  await expect(header(page).getByRole("button", { name: "Menú de perfil" })).toHaveCount(0);
  expect(events.some((event) => event.path === "/logout" && event.method === "POST")).toBe(true);
});

test("signed-in shared header on /servicios shows the profile menu and hides the auth links", async ({ page }) => {
  await installHeaderMocks(page);
  await signIn(page);
  await page.goto("/servicios");

  await expect(header(page).getByRole("button", { name: "Menú de perfil" })).toBeVisible();
  await expect(header(page).getByRole("link", { name: "Iniciar sesión" })).toHaveCount(0);
  await expect(header(page).getByRole("link", { name: "Crear cuenta" })).toHaveCount(0);
});

test("mobile navigation offers profile settings and sign-out instead of the auth links", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installHeaderMocks(page);
  await signIn(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Abrir menú" }).click();
  const mobileNav = page.getByRole("navigation", { name: "Navegación móvil" });
  await expect(mobileNav.getByRole("link", { name: "Configuración del perfil" })).toHaveAttribute("href", "/cuenta/perfil");
  await expect(mobileNav.getByRole("button", { name: "Cerrar sesión" })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Iniciar sesión" })).toHaveCount(0);
  await expect(mobileNav.getByRole("link", { name: "Crear cuenta" })).toHaveCount(0);
});
