import { expect, test, type Page } from "@playwright/test";

const invitationKey = "amira-driver-invitation";
const invitationToken = "a".repeat(43);
const confirmedUser = {
  id: "confirmed-driver",
  aud: "authenticated",
  role: "authenticated",
  email: "driver@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

function accessToken(aal: "aal1" | "aal2", id = `${aal}-access-token`) {
  const payload = Buffer.from(JSON.stringify({ aal, exp: 2000000000, sub: confirmedUser.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.${id}`;
}

function authSession(aal: "aal1" | "aal2", id = `${aal}-access-token`) {
  const expiresIn = 3600;
  return {
    access_token: accessToken(aal, id),
    token_type: "bearer",
    expires_in: expiresIn,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    refresh_token: "local-test-refresh-token",
    user: confirmedUser,
  };
}

async function installInvitationAuth(page: Page, options: { completeMfa?: boolean } = {}) {
  const events: Array<{ path: string; method: string; body?: Record<string, unknown> }> = [];
  let releaseAcceptance!: () => void;
  const acceptanceGate = new Promise<void>((resolve) => { releaseAcceptance = resolve; });
  let aal: "aal1" | "aal2" = "aal1";
  let userConfirmed = true;
  let acceptanceStatus = 200;
  const headers = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info", "Access-Control-Allow-Methods": "GET,POST,OPTIONS" };

  await page.addInitScript((token) => {
    window.sessionStorage.setItem("amira-driver-invitation", token);
  }, invitationToken);
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    let body: Record<string, unknown> = {};
    try { body = request.postDataJSON() as Record<string, unknown>; } catch { /* empty body */ }
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    events.push({ path, method: request.method(), body });
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: authSession("aal1", "password-aal1-token"), headers });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "refresh_token") {
      await route.fulfill({ json: authSession(aal, `${aal}-refreshed-token`), headers });
      return;
    }
    if (path === "/user" && request.method() === "GET") {
      const user = !userConfirmed
        ? { ...confirmedUser, email_confirmed_at: null, confirmed_at: null }
        : aal === "aal1"
          ? { ...confirmedUser, factors: [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" }] }
          : confirmedUser;
      await route.fulfill({ json: user, headers });
      return;
    }
    if (path === "/factors" && request.method() === "GET") {
      await route.fulfill({ json: { all: [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" }], phone: [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" }], totp: [] }, headers });
      return;
    }
    if (path === "/factors/factor-sms-1/challenge" && request.method() === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 }, headers });
      return;
    }
    if (path === "/factors/factor-sms-1/verify" && request.method() === "POST") {
      aal = "aal2";
      await route.fulfill({ json: authSession("aal2", "verified-aal2-token"), headers });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected auth request: ${request.method()} ${path}` }, headers });
  });
  await page.route("**/api/account/me", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    await route.fulfill({ json: { user_id: "account-test-1", role: "company_driver", profile_id: "driver-profile-1" }, headers });
  });
  await page.route("**/api/driver-invitations/accept", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    events.push({ path: "/api/driver-invitations/accept", method: route.request().method() });
    await acceptanceGate;
    await route.fulfill({ status: acceptanceStatus, json: { accepted: acceptanceStatus === 200 }, headers });
  });

  await page.goto("/login?next=%2Finvitacion%2Fconductor%2Faceptar");
  await page.locator("#auth-email").fill(confirmedUser.email);
  await page.locator("#auth-password").fill("test-password-not-a-secret");
  await page.locator("form.auth-form button[type=submit]").click();
  if (options.completeMfa !== false) {
    await page.locator("#auth-code").fill("246810");
    await page.locator("form.auth-form button[type=submit]").click();
  } else {
    await page.goto("/invitacion/conductor/aceptar");
  }
  await expect(page).toHaveURL(/\/invitacion\/conductor\/aceptar$/);

  return {
    events,
    releaseAcceptance,
    setUserConfirmed: (confirmed: boolean) => { userConfirmed = confirmed; },
    setAcceptanceStatus: (status: number) => { acceptanceStatus = status; },
  };
}

test("driver invitation removes the token from the address bar and offers signup or sign-in", async ({ page }) => {
  const token = "a".repeat(43);
  await page.goto(`/invitacion/conductor#token=${token}`);

  await expect(page.getByRole("heading", { name: "Únete a un equipo de Amira" })).toBeVisible();
  await expect(page).toHaveURL("/invitacion/conductor");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("amira-driver-invitation"))).toBe(token);
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Finvitacion%2Fconductor%2Faceptar");
  await page.getByRole("link", { name: "Crear cuenta desde la invitación" }).click();
  await expect(page).toHaveURL("/registro?intent=invite");
  await expect(page.locator("input[type=email]")).toBeVisible();
});

test("driver invitation is accepted only after deliberate click and disables repeated submission", async ({ page }) => {
  const { events, releaseAcceptance } = await installInvitationAuth(page);
  const button = page.locator("button.auth-submit");
  await expect.poll(async () => await button.count() === 1 || events.some((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toBe(true);
  expect(events.filter((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toEqual([]);
  await expect(page.getByRole("button", { name: "Aceptar invitaci\u00f3n" })).toBeEnabled();
  await expect(button).toBeEnabled();
  await button.click();
  await expect(button).toBeDisabled();
  await expect(button).toContainText("Aceptando");
  await button.click({ force: true });
  expect(events.filter((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toHaveLength(1);
  releaseAcceptance();

  await expect(page.getByRole("status")).toContainText("Aceptaste la invitaci\u00f3n");
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBeNull();
});

test("driver invitation requires confirmed email and SMS aal2 before accepting", async ({ page }) => {
  const { events, setUserConfirmed } = await installInvitationAuth(page);
  const button = page.locator("button.auth-submit");

  await expect(button).toBeEnabled();
  setUserConfirmed(false);
  await button.click();
  await expect(page.getByRole("status")).toContainText("correo confirmado");
  expect(events.filter((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toEqual([]);
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBe(invitationToken);
});

test("driver invitation keeps the acceptance action unavailable at aal1", async ({ page }) => {
  const aal1 = await installInvitationAuth(page, { completeMfa: false });
  await expect(page.getByRole("status")).toContainText("verificación SMS");
  await expect(page.locator("button.auth-submit")).toHaveCount(0);
  expect(aal1.events.filter((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toEqual([]);
});

test("driver invitation keeps the token and shows a safe failure when acceptance is rejected", async ({ page }) => {
  const { events, releaseAcceptance, setAcceptanceStatus } = await installInvitationAuth(page);
  setAcceptanceStatus(410);

  await page.locator("button.auth-submit").click();
  await expect.poll(() => events.filter((event) => event.path === "/api/driver-invitations/accept" && event.method === "POST")).toHaveLength(1);
  releaseAcceptance();

  await expect(page.locator("p.auth-error")).toContainText("Puede haber vencido");
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBe(invitationToken);
});

test("driver invitation rejects a missing token without sending an acceptance request", async ({ page }) => {
  await page.goto("/invitacion/conductor/aceptar");
  await expect(page.locator("p.auth-error")).toContainText("No pudimos aceptar");
  await expect(page.locator("button.auth-submit")).toHaveCount(0);
});
