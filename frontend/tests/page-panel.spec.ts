import { expect, test, type Page } from "@playwright/test";
import { locationsResponse } from "./support/catalog-fixtures";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

const user = {
  id: "user-panel-1",
  aud: "authenticated",
  role: "authenticated",
  email: "persona@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

// The panel is a protected page, so the fake session must be AAL2 (SMS-verified), as on the other private pages.
function accessToken(aal: "aal1" | "aal2" = "aal2") {
  const payload = Buffer.from(JSON.stringify({ aal, exp: 2000000000, sub: user.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.panel-access-token`;
}

function session(aal: "aal1" | "aal2" = "aal2") {
  return {
    access_token: accessToken(aal),
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: "refresh-test-token",
    user,
  };
}

// Fake Supabase Auth, the account role for the given role, and an empty provider services list.
async function installPanelMocks(page: Page, role: string | null, aal: "aal1" | "aal2" = "aal2") {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();

    if (method === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ headers: corsHeaders, json: session(aal) });
      return;
    }
    if (path === "/user" && method === "GET") {
      await route.fulfill({ headers: corsHeaders, json: { ...user, factors: [] } });
      return;
    }
    await route.fulfill({ status: 404, headers: corsHeaders, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await page.route("**/api/locations", async (route) => route.fulfill({ json: locationsResponse }));
  await page.route("**/api/chats/unread", async (route) => route.fulfill({ json: { total: 0 } }));
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-panel-1", role, profile_id: null } }));
  await page.route("**/api/provider/services**", async (route) => route.fulfill({ json: { items: [], offset: 0, limit: 20, total: 0 } }));
}

// Signs in through the real login form so the Supabase client stores the session the panel reads.
async function signIn(page: Page) {
  const tokenRequest = page.waitForRequest((request) => request.url().includes("/auth/v1/token") && request.method() === "POST");
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await tokenRequest;
}

// Scoped to <main> so the shared header links (for example "Mis servicios") do not collide with the panel buttons.
const panel = (page: Page) => page.getByRole("main");

test("independent driver sees the provider action buttons without the invitations button", async ({ page }) => {
  await installPanelMocks(page, "independent_driver");
  await signIn(page);
  await page.goto("/panel");

  await expect(panel(page).getByRole("heading", { name: "Panel del proveedor" })).toBeVisible();
  await expect(panel(page).getByRole("link", { name: "Mensajes" })).toHaveAttribute("href", "/mensajes");
  await expect(panel(page).getByRole("link", { name: "Servicios", exact: true })).toHaveAttribute("href", "/cuenta/servicios");
  await expect(panel(page).getByRole("link", { name: "Configuración del perfil" })).toHaveAttribute("href", "/cuenta/perfil");
  await expect(panel(page).getByRole("link", { name: "Invitaciones" })).toHaveCount(0);
});

test("company owner sees the provider buttons and the invitations button", async ({ page }) => {
  await installPanelMocks(page, "company_owner");
  await signIn(page);
  await page.goto("/panel");

  await expect(panel(page).getByRole("link", { name: "Mensajes" })).toHaveAttribute("href", "/mensajes");
  await expect(panel(page).getByRole("link", { name: "Servicios", exact: true })).toHaveAttribute("href", "/cuenta/servicios");
  await expect(panel(page).getByRole("link", { name: "Configuración del perfil" })).toHaveAttribute("href", "/cuenta/perfil");
  await expect(panel(page).getByRole("link", { name: "Invitaciones" })).toHaveAttribute("href", "/cuenta/invitaciones");
});

test("company driver sees the assigned services area and the profile button", async ({ page }) => {
  await installPanelMocks(page, "company_driver");
  await signIn(page);
  await page.goto("/panel");

  await expect(panel(page).getByRole("heading", { name: "Panel del proveedor" })).toBeVisible();
  await expect(panel(page).getByText("Aún no tienes servicios")).toBeVisible();
  await expect(panel(page).getByRole("link", { name: "Mi perfil" })).toHaveAttribute("href", "/cuenta/perfil");
});

test("client is redirected to /servicios", async ({ page }) => {
  await installPanelMocks(page, "client");
  await signIn(page);
  await page.goto("/panel");

  await expect(page).toHaveURL(/\/servicios$/);
});

test("AAL1 session with SMS still pending sees the SMS prompt, not the sign-in prompt", async ({ page }) => {
  await installPanelMocks(page, "independent_driver", "aal1");
  await signIn(page);
  await page.goto("/panel");

  await expect(panel(page).getByRole("alert")).toHaveText("Verifica tu teléfono por SMS para ver tu panel.");
  await expect(panel(page).getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fpanel");
});

test("signed-out visitor sees the sign-in prompt that returns to /panel", async ({ page }) => {
  await installPanelMocks(page, null);
  await page.goto("/panel");

  await expect(panel(page).getByRole("alert")).toContainText("Inicia sesión");
  await expect(panel(page).getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fpanel");
});

test("provider panel links to the shared trips page", async ({ page }) => {
  await installPanelMocks(page, "independent_driver");
  await signIn(page);
  await page.goto("/panel");

  await expect(panel(page).getByRole("link", { name: "Viajes compartidos" })).toHaveAttribute("href", "/cuenta/viajes-compartidos");
});
