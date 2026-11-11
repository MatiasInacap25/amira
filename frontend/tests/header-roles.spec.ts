import { expect, test, type Page } from "@playwright/test";
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

// Roles that run the provider and company panel. company_driver is not a provider role for the request inbox, but it still uses the panel header.
const PANEL_ROLES = ["independent_driver", "company_owner", "company_driver"] as const;
const PUBLIC_SEARCH_LINKS = ["Buscar servicios", "Rutas compartidas", "Cómo funciona"] as const;

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

// Signs in through the real login and MFA screens with the given role returned by /api/account/me.
async function signInWithRole(page: Page, role: string, next: string) {
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
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role, profile_id: null } }));
  await page.route("**/api/provider/requests**", async (route) => route.fulfill({
    json: { items: [], total: 0, limit: 20, offset: 0, counts: { pending: 0, accepted: 0, rejected: 0 } },
  }));

  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(new RegExp(`${next.replace(/[/]/g, "\\/")}$`));
}

function desktopNav(page: Page) {
  return page.getByRole("navigation", { name: "Navegación principal" });
}

function mobileNav(page: Page) {
  return page.getByRole("navigation", { name: "Navegación móvil" });
}

for (const role of PANEL_ROLES) {
  test(`${role} sees no public search links in the desktop header, on the marketplace or the home page`, async ({ page }) => {
    await signInWithRole(page, role, "/servicios");

    for (const name of PUBLIC_SEARCH_LINKS) {
      await expect(desktopNav(page).getByRole("link", { name })).toHaveCount(0);
    }
    await expect(page.locator("header.site-header").getByRole("link", { name: "Buscar un servicio" })).toHaveCount(0);

    await page.goto("/");
    for (const name of PUBLIC_SEARCH_LINKS) {
      await expect(desktopNav(page).getByRole("link", { name })).toHaveCount(0);
    }
  });

  test(`${role} sees no public search links in the mobile menu`, async ({ page }) => {
    await signInWithRole(page, role, "/servicios");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Abrir menú" }).click();

    for (const name of PUBLIC_SEARCH_LINKS) {
      await expect(mobileNav(page).getByRole("link", { name })).toHaveCount(0);
    }
    await expect(mobileNav(page).getByRole("link", { name: "Mis servicios" })).toBeVisible();
  });
}

test("anonymous visitors keep the public search links in the desktop header and the mobile menu", async ({ page }) => {
  await page.goto("/servicios");
  for (const name of PUBLIC_SEARCH_LINKS) {
    await expect(desktopNav(page).getByRole("link", { name })).toBeVisible();
  }
  await expect(page.locator("header.site-header").getByRole("link", { name: "Buscar un servicio" })).toBeVisible();

  await page.goto("/");
  for (const name of PUBLIC_SEARCH_LINKS) {
    await expect(desktopNav(page).getByRole("link", { name })).toBeVisible();
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  for (const name of PUBLIC_SEARCH_LINKS) {
    await expect(mobileNav(page).getByRole("link", { name })).toBeVisible();
  }
});

test("anonymous visitors see no provider-only Mis servicios link in the header or the mobile menu", async ({ page }) => {
  await page.goto("/servicios");
  await expect(desktopNav(page).getByRole("link", { name: "Buscar servicios" })).toBeVisible();
  await expect(desktopNav(page).getByRole("link", { name: "Mis servicios" })).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await expect(mobileNav(page).getByRole("link", { name: "Buscar servicios" })).toBeVisible();
  await expect(mobileNav(page).getByRole("link", { name: "Mis servicios" })).toHaveCount(0);
});

test("customers see no provider-only Mis servicios link in the header", async ({ page }) => {
  await signInWithRole(page, "client", "/servicios");
  await expect(desktopNav(page).getByRole("link", { name: "Buscar servicios" })).toBeVisible();
  await expect(desktopNav(page).getByRole("link", { name: "Mis servicios" })).toHaveCount(0);
});

test("customers keep the public search links in the desktop header", async ({ page }) => {
  await signInWithRole(page, "client", "/servicios");

  for (const name of PUBLIC_SEARCH_LINKS) {
    await expect(desktopNav(page).getByRole("link", { name })).toBeVisible();
  }
  await expect(page.locator("header.site-header").getByRole("link", { name: "Buscar un servicio" })).toBeVisible();
});
