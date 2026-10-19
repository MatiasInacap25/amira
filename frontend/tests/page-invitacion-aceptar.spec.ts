import { expect, test, type Page } from "@playwright/test";

const invitationKey = "amira-driver-invitation";
const invitationToken = "a".repeat(43);
const acceptPath = "/invitacion/conductor/aceptar";
const acceptReturnPath = "/login?next=%2Finvitacion%2Fconductor%2Faceptar";
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

// Signs in through the real login form with the given invitation token retained, then lands on the accept page.
// Accept responses use the status the test sets; the request count is recorded for assertions.
async function signInWithInvitation(page: Page, options: { completeMfa?: boolean } = {}) {
  const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info", "Access-Control-Allow-Methods": "GET,POST,OPTIONS" };
  const accepts: string[] = [];
  let aal: "aal1" | "aal2" = "aal1";
  let acceptStatus = 200;

  await page.addInitScript((token) => {
    window.sessionStorage.setItem("amira-driver-invitation", token);
  }, invitationToken);
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: authSession("aal1", "password-aal1-token"), headers: cors });
      return;
    }
    if (path === "/user" && request.method() === "GET") {
      const user = aal === "aal1"
        ? { ...confirmedUser, factors: [{ id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" }] }
        : confirmedUser;
      await route.fulfill({ json: user, headers: cors });
      return;
    }
    if (path === "/factors" && request.method() === "GET") {
      const factor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };
      await route.fulfill({ json: { all: [factor], phone: [factor], totp: [] }, headers: cors });
      return;
    }
    if (path === "/factors/factor-sms-1/challenge" && request.method() === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 }, headers: cors });
      return;
    }
    if (path === "/factors/factor-sms-1/verify" && request.method() === "POST") {
      aal = "aal2";
      await route.fulfill({ json: authSession("aal2", "verified-aal2-token"), headers: cors });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected auth request: ${request.method()} ${path}` }, headers: cors });
  });
  await page.route("**/api/account/me", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    await route.fulfill({ json: { user_id: "account-test-1", role: "company_driver", profile_id: "driver-profile-1" }, headers: cors });
  });
  await page.route("**/api/driver-invitations/accept", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    accepts.push(route.request().method());
    await route.fulfill({ status: acceptStatus, json: { accepted: acceptStatus === 200 }, headers: cors });
  });

  await page.goto(`/login?next=%2Finvitacion%2Fconductor%2Faceptar`);
  await page.locator("#auth-email").fill(confirmedUser.email);
  await page.locator("#auth-password").fill("test-password-not-a-secret");
  await page.locator("form.auth-form button[type=submit]").click();
  if (options.completeMfa !== false) {
    await page.locator("#auth-code").fill("246810");
    await page.locator("form.auth-form button[type=submit]").click();
  } else {
    await page.goto(acceptPath);
  }
  await expect(page).toHaveURL(/\/invitacion\/conductor\/aceptar$/);

  return {
    accepts,
    setAcceptStatus: (status: number) => { acceptStatus = status; },
  };
}

function acceptPanel(page: Page) {
  return page.locator("section.auth-form-panel");
}

test("signed-out visitor with a retained token is asked to sign in and offered account creation", async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem("amira-driver-invitation", token);
  }, invitationToken);

  await page.goto(acceptPath);

  await expect(acceptPanel(page).getByRole("status")).toHaveText("Inicia sesión con el correo confirmado que recibió la invitación.");
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", acceptReturnPath);
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro?intent=invite");
  await expect(page.getByRole("button", { name: "Aceptar invitación" })).toHaveCount(0);
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBe(invitationToken);
});

test("malformed retained token shows the safe error and no accept action", async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem("amira-driver-invitation", "token con espacios");
  });

  await page.goto(acceptPath);

  await expect(page.getByRole("heading", { name: "Confirmar invitación" })).toBeVisible();
  await expect(acceptPanel(page).getByRole("alert")).toHaveText("No pudimos aceptar la invitación. Puede haber vencido, sido revocada o no corresponder a esta cuenta.");
  await expect(page.getByRole("button", { name: "Aceptar invitación" })).toHaveCount(0);
});

test("signed-in driver with confirmed SMS sees the ready state and the accept button", async ({ page }) => {
  await signInWithInvitation(page);

  await expect(acceptPanel(page).getByRole("status")).toHaveText("La invitación está lista para aceptar.");
  await expect(page.getByRole("button", { name: "Aceptar invitación" })).toBeEnabled();
});

test("aal1 session shows the SMS verification link to continue", async ({ page }) => {
  await signInWithInvitation(page, { completeMfa: false });

  await expect(acceptPanel(page).getByRole("status")).toHaveText("Completa la verificación SMS antes de aceptar la invitación.");
  await expect(page.getByRole("link", { name: "Continuar verificación" })).toHaveAttribute("href", acceptReturnPath);
  await expect(page.getByRole("button", { name: "Aceptar invitación" })).toHaveCount(0);
});

test("wrong-account rejection shows the safe error and re-enables the button for a retry", async ({ page }) => {
  const { accepts, setAcceptStatus } = await signInWithInvitation(page);
  setAcceptStatus(403);
  const button = page.getByRole("button", { name: "Aceptar invitación" });
  await expect(button).toBeEnabled();

  await button.click();

  await expect(acceptPanel(page).getByRole("alert")).toContainText("no corresponder a esta cuenta");
  await expect(button).toBeEnabled();
  await expect(button).toHaveText("Aceptar invitación");
  expect(accepts).toHaveLength(1);
});

test("server error during acceptance is announced as an alert and keeps the retained token", async ({ page }) => {
  const { setAcceptStatus } = await signInWithInvitation(page);
  setAcceptStatus(500);

  await page.getByRole("button", { name: "Aceptar invitación" }).click();

  await expect(acceptPanel(page).getByRole("alert")).toContainText("No pudimos aceptar la invitación");
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBe(invitationToken);
});

test("successful acceptance removes the action and links to Amira", async ({ page }) => {
  await signInWithInvitation(page);

  await page.getByRole("button", { name: "Aceptar invitación" }).click();

  await expect(acceptPanel(page).getByRole("status")).toHaveText("Aceptaste la invitación y ya formas parte de la empresa.");
  await expect(page.getByRole("button", { name: "Aceptar invitación" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Ir a Amira" })).toHaveAttribute("href", "/servicios");
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBeNull();
});

test("acceptance page fits a 320px viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await page.addInitScript((token) => {
    window.sessionStorage.setItem("amira-driver-invitation", token);
  }, invitationToken);
  await page.goto(acceptPath);
  await expect(page.getByRole("heading", { name: "Confirmar invitación" })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
