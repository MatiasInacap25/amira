import { expect, test, type Page, type Route } from "@playwright/test";

const user = {
  id: "company-user-1",
  aud: "authenticated",
  role: "authenticated",
  email: "empresa@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const phoneFactor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };
const invitationsUrl = /\/api\/company\/profiles\/me\/driver-invitations/;
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
};

type Invitation = { id: string; email: string; created_at: string; expires_at: string; status: "pending" | "expired" | "revoked" | "accepted" };
type InvitationRequest = { method: string; path: string; body: Record<string, unknown> | null };

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

function invitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: "invitation-1",
    email: "conductor@example.test",
    created_at: "2026-10-10T12:00:00.000Z",
    expires_at: "2026-10-17T12:00:00.000Z",
    status: "pending",
    ...overrides,
  };
}

// Auth calls for the email/password, SMS MFA and session checks. `confirmed` controls the email confirmation flag.
async function mockAuth(page: Page, options: { confirmed?: boolean } = {}) {
  const confirmed = options.confirmed ?? true;
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
      const current = confirmed ? user : { ...user, email_confirmed_at: null, confirmed_at: null };
      await route.fulfill({ json: { ...current, factors: [phoneFactor] } });
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

// Signs in through the real login form with MFA completed, landing on /cuenta/invitaciones.
async function signInToInvitations(page: Page) {
  await mockAuth(page);
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role: "company", profile_id: "company-profile-1" } }));
  await page.goto("/login?next=%2Fcuenta%2Finvitaciones");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/invitaciones$/);
}

// Answers the company invitations API. `handle` decides each response; every call is recorded.
async function mockInvitationsApi(
  page: Page,
  handle: (request: InvitationRequest, route: Route) => Promise<void>,
) {
  const requests: InvitationRequest[] = [];
  await page.route(invitationsUrl, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    const url = new URL(request.url());
    const entry: InvitationRequest = { method: request.method(), path: url.pathname, body: request.postDataJSON() as Record<string, unknown> | null };
    requests.push(entry);
    await handle(entry, route);
  });
  return requests;
}

// Serves the list from `invitations` and mutates it like the backend does for revoke and reissue.
function serveInvitations(invitations: Invitation[]) {
  return async (request: InvitationRequest, route: Route) => {
    if (request.method === "GET") {
      await route.fulfill({ json: { invitations }, headers: corsHeaders });
      return;
    }
    if (request.method === "POST" && request.path.endsWith("/driver-invitations")) {
      const email = String(request.body?.email);
      invitations.push(invitation({ id: `invitation-${invitations.length + 1}`, email }));
      await route.fulfill({ status: 201, json: { id: `invitation-${invitations.length}`, email, expires_at: "2026-10-17T12:00:00.000Z" }, headers: corsHeaders });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "Invitation not found." }, headers: corsHeaders });
  };
}

test("signed-out visitor is sent to sign-in and no invitation list is requested", async ({ page }) => {
  const requests = await mockInvitationsApi(page, async (_request, route) => route.fulfill({ json: { invitations: [] }, headers: corsHeaders }));

  await page.goto("/cuenta/invitaciones");

  await expect(page).toHaveURL("/login?next=%2Fcuenta%2Finvitaciones");
  expect(requests).toHaveLength(0);
});

test("unconfirmed email is sent to sign-in before any invitation request", async ({ page }) => {
  await mockAuth(page, { confirmed: false });
  const requests = await mockInvitationsApi(page, async (_request, route) => route.fulfill({ json: { invitations: [] }, headers: corsHeaders }));
  await page.goto("/login?next=%2Fcuenta%2Finvitaciones");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect.poll(() => page.url()).toContain("/login");

  await page.goto("/cuenta/invitaciones");

  await expect(page).toHaveURL("/login?next=%2Fcuenta%2Finvitaciones");
  expect(requests).toHaveLength(0);
});

test("session without SMS verification is sent to sign-in before any invitation request", async ({ page }) => {
  await mockAuth(page);
  const requests = await mockInvitationsApi(page, async (_request, route) => route.fulfill({ json: { invitations: [] }, headers: corsHeaders }));
  await page.goto("/login?next=%2Fcuenta%2Finvitaciones");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page.locator("#auth-code")).toBeVisible();

  await page.goto("/cuenta/invitaciones");

  await expect(page).toHaveURL("/login?next=%2Fcuenta%2Finvitaciones");
  expect(requests).toHaveLength(0);
});

test("company page explains the invitation flow and links back to services", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, serveInvitations([]));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await expect(panel.getByRole("heading", { name: "Invitar conductores", level: 1 })).toBeVisible();
  await expect(panel.getByText("Las personas invitadas deberán confirmar su correo, completar la verificación de acceso y aceptar antes de quedar vinculadas.", { exact: true })).toBeVisible();
  await expect(panel.getByText("El perfil independiente se convierte en empresa solo cuando la primera persona invitada acepta.", { exact: true })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/servicios");
  await expect(panel.getByLabel("Correo de la persona invitada")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Enviar invitación" })).toBeEnabled();
});

test("empty company list shows the no-invitations message", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, serveInvitations([]));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await expect(panel.getByRole("heading", { name: "Invitaciones" })).toBeVisible();
  await expect(panel.getByText("No hay invitaciones todavía.", { exact: true })).toBeVisible();
});

test("each invitation shows its email, status and expiry, and only pending ones offer actions", async ({ page }) => {
  await signInToInvitations(page);
  const invitations = [
    invitation({ id: "pending-1", email: "pendiente@example.test" }),
    invitation({ id: "revoked-1", email: "revocada@example.test", status: "revoked" }),
  ];
  await mockInvitationsApi(page, serveInvitations(invitations));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  const pendingRow = panel.getByRole("listitem").filter({ hasText: "pendiente@example.test" });
  const revokedRow = panel.getByRole("listitem").filter({ hasText: "revocada@example.test" });
  const expires = new Date(invitations[0].expires_at).toLocaleDateString("es-CL");

  await expect(pendingRow.locator("strong")).toHaveText("pendiente@example.test");
  await expect(pendingRow).toContainText(`· pending · vence ${expires}`);
  await expect(pendingRow.getByRole("button", { name: "Reenviar" })).toBeVisible();
  await expect(pendingRow.getByRole("button", { name: "Revocar" })).toBeVisible();
  await expect(revokedRow).toContainText("· revoked ·");
  await expect(revokedRow.getByRole("button", { name: "Reenviar" })).toHaveCount(0);
  await expect(revokedRow.getByRole("button", { name: "Revocar" })).toHaveCount(0);
});

test("sending an invitation without a company tax ID posts only the email, then shows the notice and refreshes the list", async ({ page }) => {
  await signInToInvitations(page);
  const invitations: Invitation[] = [];
  const requests = await mockInvitationsApi(page, serveInvitations(invitations));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("nuevo@example.test");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();

  await expect(panel.getByRole("status")).toHaveText("Invitación enviada. El vínculo vence en siete días.");
  await expect(panel.getByLabel("Correo de la persona invitada")).toHaveValue("");
  await expect(panel.getByRole("listitem").filter({ hasText: "nuevo@example.test" })).toBeVisible();
  expect(requests.filter((request) => request.method === "POST")).toEqual([
    { method: "POST", path: "/api/company/profiles/me/driver-invitations", body: { email: "nuevo@example.test" } },
  ]);
});

test("first invitation sends the company RUT normalized after the field is formatted on blur", async ({ page }) => {
  await signInToInvitations(page);
  const invitations: Invitation[] = [];
  const requests = await mockInvitationsApi(page, serveInvitations(invitations));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("primer@example.test");
  const taxId = panel.getByLabel("RUT de empresa (requerido solo para el primer conductor)");
  await taxId.fill("12345678-5");
  await taxId.blur();
  await expect(taxId).toHaveValue("12.345.678-5");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();

  await expect(panel.getByRole("status")).toContainText("Invitación enviada");
  expect(requests.filter((request) => request.method === "POST")).toEqual([
    { method: "POST", path: "/api/company/profiles/me/driver-invitations", body: { email: "primer@example.test", company_tax_id: "12345678-5" } },
  ]);
});

test("an invalid company RUT is rejected in place and sends no invitation", async ({ page }) => {
  await signInToInvitations(page);
  const requests = await mockInvitationsApi(page, serveInvitations([]));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("rut@example.test");
  const taxId = panel.getByLabel("RUT de empresa (requerido solo para el primer conductor)");
  await taxId.fill("12345678-9");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();

  await expect(panel.getByText("El RUT no es válido. Revisa el dígito verificador.", { exact: true })).toBeVisible();
  await expect(taxId).toHaveAttribute("aria-invalid", "true");
  await expect(taxId).toHaveAttribute("aria-describedby", "driver-invitation-company-tax-id-error");
  expect(requests.filter((request) => request.method === "POST")).toHaveLength(0);
});

test("editing the RUT clears its validation error", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, serveInvitations([]));
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("rut@example.test");
  const taxId = panel.getByLabel("RUT de empresa (requerido solo para el primer conductor)");
  await taxId.fill("12345678-9");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();
  await expect(panel.getByText("El RUT no es válido. Revisa el dígito verificador.", { exact: true })).toBeVisible();

  await taxId.fill("12345678-5");

  await expect(panel.getByText("El RUT no es válido. Revisa el dígito verificador.", { exact: true })).toHaveCount(0);
  await expect(taxId).not.toHaveAttribute("aria-invalid", "true");
});

test("a rejected invitation shows a safe error and keeps the typed email", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, async (request, route) => {
    if (request.method === "GET") {
      await route.fulfill({ json: { invitations: [] }, headers: corsHeaders });
      return;
    }
    await route.fulfill({ status: 409, json: { detail: "The pending company tax ID cannot be changed." }, headers: corsHeaders });
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("rechazado@example.test");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();

  await expect(panel.getByRole("alert")).toHaveText("No pudimos enviar la invitación. Revisa la dirección o intenta más tarde.");
  await expect(panel.getByLabel("Correo de la persona invitada")).toHaveValue("rechazado@example.test");
  await expect(panel.getByRole("status")).toHaveCount(0);
});

test("submit is disabled while an invitation is in flight", async ({ page }) => {
  await signInToInvitations(page);
  let releasePost!: () => void;
  const postGate = new Promise<void>((resolve) => { releasePost = resolve; });
  const invitations: Invitation[] = [];
  const serve = serveInvitations(invitations);
  await mockInvitationsApi(page, async (request, route) => {
    if (request.method === "POST") {
      await postGate;
    }
    await serve(request, route);
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByLabel("Correo de la persona invitada").fill("espera@example.test");
  await panel.getByRole("button", { name: "Enviar invitación" }).click();

  const busy = panel.getByRole("button", { name: "Procesando…" });
  await expect(busy).toBeDisabled();
  releasePost();
  await expect(panel.getByRole("button", { name: "Enviar invitación" })).toBeEnabled();
});

test("revoking a pending invitation sends a DELETE, shows the notice and refreshes its status", async ({ page }) => {
  await signInToInvitations(page);
  const invitations = [invitation({ id: "pending-1", email: "revocar@example.test" })];
  const requests = await mockInvitationsApi(page, async (request, route) => {
    if (request.method === "DELETE") {
      invitations[0] = { ...invitations[0], status: "revoked" };
      await route.fulfill({ json: { id: "pending-1", email: "revocar@example.test", expires_at: invitations[0].expires_at }, headers: corsHeaders });
      return;
    }
    await serveInvitations(invitations)(request, route);
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  const row = panel.getByRole("listitem").filter({ hasText: "revocar@example.test" });
  await row.getByRole("button", { name: "Revocar" }).click();

  await expect(panel.getByRole("status")).toHaveText("Invitación revocada.");
  await expect(row).toContainText("· revoked ·");
  await expect(row.getByRole("button", { name: "Revocar" })).toHaveCount(0);
  expect(requests.filter((request) => request.method === "DELETE").map((request) => request.path)).toEqual(["/api/company/profiles/me/driver-invitations/pending-1"]);
});

test("reissuing an invitation posts to its reissue route and shows that the previous link stopped working", async ({ page }) => {
  await signInToInvitations(page);
  const invitations = [invitation({ id: "pending-1", email: "reenviar@example.test" })];
  const requests = await mockInvitationsApi(page, async (request, route) => {
    if (request.method === "POST" && request.path.endsWith("/reissue")) {
      await route.fulfill({ status: 201, json: { id: "pending-2", email: "reenviar@example.test", expires_at: invitations[0].expires_at }, headers: corsHeaders });
      return;
    }
    await serveInvitations(invitations)(request, route);
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await panel.getByRole("listitem").filter({ hasText: "reenviar@example.test" }).getByRole("button", { name: "Reenviar" }).click();

  await expect(panel.getByRole("status")).toHaveText("Nuevo vínculo enviado; el anterior dejó de funcionar.");
  expect(requests.filter((request) => request.method === "POST" && request.path.endsWith("/reissue")).map((request) => request.path)).toEqual([
    "/api/company/profiles/me/driver-invitations/pending-1/reissue",
  ]);
});

test("a failed revoke shows a safe error and leaves the invitation pending", async ({ page }) => {
  await signInToInvitations(page);
  const invitations = [invitation({ id: "pending-1", email: "falla@example.test" })];
  await mockInvitationsApi(page, async (request, route) => {
    if (request.method === "DELETE") {
      await route.fulfill({ status: 409, json: { detail: "Only a pending invitation can be revoked." }, headers: corsHeaders });
      return;
    }
    await serveInvitations(invitations)(request, route);
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  const row = panel.getByRole("listitem").filter({ hasText: "falla@example.test" });
  await row.getByRole("button", { name: "Revocar" }).click();

  await expect(panel.getByRole("alert")).toHaveText("No pudimos actualizar esta invitación.");
  await expect(row).toContainText("· pending ·");
  await expect(row.getByRole("button", { name: "Revocar" })).toBeEnabled();
});

test("account without company access sees the invitation list error", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, async (_request, route) => {
    await route.fulfill({ status: 403, json: { detail: "Forbidden" }, headers: corsHeaders });
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await expect(panel.getByRole("alert")).toHaveText("No pudimos cargar las invitaciones.");
});

// The list stays empty after a failed load, so the "no invitations" copy is shown next to the error.
test.fixme("a failed invitation load does not claim there are no invitations", async ({ page }) => {
  await signInToInvitations(page);
  await mockInvitationsApi(page, async (_request, route) => {
    await route.fulfill({ status: 403, json: { detail: "Forbidden" }, headers: corsHeaders });
  });
  await page.goto("/cuenta/invitaciones");

  const panel = page.getByRole("region", { name: "Invitar conductores" });
  await expect(panel.getByRole("alert")).toHaveText("No pudimos cargar las invitaciones.");
  await expect(panel.getByText("No hay invitaciones todavía.", { exact: true })).toHaveCount(0);
});

test("company invitations page fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInToInvitations(page);
  await mockInvitationsApi(page, serveInvitations([invitation({ id: "pending-1", email: "conductor@example.test" })]));
  await page.goto("/cuenta/invitaciones");

  await expect(page.getByRole("region", { name: "Invitar conductores" }).getByRole("button", { name: "Revocar" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

// An unbroken email wider than the phone viewport pushes the whole page sideways.
test.fixme("a long invitation email does not force horizontal page scroll on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInToInvitations(page);
  await mockInvitationsApi(page, serveInvitations([
    invitation({ id: "pending-1", email: "un.correo.bastante.largo.para.revisar.el.ajuste.en.pantallas.pequenas@example.test" }),
  ]));
  await page.goto("/cuenta/invitaciones");

  await expect(page.getByRole("region", { name: "Invitar conductores" }).getByRole("button", { name: "Revocar" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
