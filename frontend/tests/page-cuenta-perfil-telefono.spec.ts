import { expect, test, type Page } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
};

const user = {
  id: "user-phone-1",
  aud: "authenticated",
  role: "authenticated",
  email: "camila@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const OLD_PHONE = "+56911111111";
const NEW_PHONE = "+56922222222";
const SMS_CODE = "123456";

function session() {
  const payload = Buffer.from(JSON.stringify({ aal: "aal2", exp: 2000000000, sub: user.id })).toString("base64url");
  return {
    access_token: `eyJhbGciOiJub25lIn0.${payload}.phone-access-token`,
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: "refresh-test-token",
    user,
  };
}

type Factor = { id: string; factor_type: "phone"; status: "verified" | "unverified"; phone: string; friendly_name: string };

type Options = { phoneAnswer?: { status: number; json: unknown } };

// Fake Supabase Auth with SMS factors and a stateful account API. Returns the request log the tests assert on.
async function installMocks(page: Page, options: Options = {}) {
  const state = {
    phone: OLD_PHONE as string | null,
    factors: [{ id: "factor-old", factor_type: "phone", status: "verified", phone: "56911111111", friendly_name: "Amira SMS" }] as Factor[],
    enrollBodies: [] as Array<Record<string, unknown>>,
    unenrolled: [] as string[],
    phonePuts: [] as Array<Record<string, unknown>>,
  };

  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });
    if (path === "/token" && url.searchParams.get("grant_type") === "password") return route.fulfill({ headers: corsHeaders, json: session() });
    if (path === "/user" && method === "GET") return route.fulfill({ headers: corsHeaders, json: { ...user, factors: state.factors } });
    if (path === "/factors" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.enrollBodies.push(body);
      const factor: Factor = { id: "factor-new", factor_type: "phone", status: "unverified", phone: String(body.phone).replace("+", ""), friendly_name: String(body.friendly_name) };
      state.factors.push(factor);
      return route.fulfill({ headers: corsHeaders, json: { id: factor.id, type: "phone", friendly_name: factor.friendly_name, phone: factor.phone } });
    }
    const challenge = path.match(/^\/factors\/([^/]+)\/challenge$/);
    if (challenge && method === "POST") {
      return route.fulfill({ headers: corsHeaders, json: { id: `challenge-${challenge[1]}`, type: "phone", expires_at: Math.floor(Date.now() / 1000) + 300 } });
    }
    const verify = path.match(/^\/factors\/([^/]+)\/verify$/);
    if (verify && method === "POST") {
      const body = request.postDataJSON() as { code?: string };
      if (body.code !== SMS_CODE) {
        return route.fulfill({ status: 422, headers: corsHeaders, json: { code: "mfa_verification_failed", msg: "Invalid MFA Phone code entered" } });
      }
      state.factors = state.factors.map((factor) => (factor.id === verify[1] ? { ...factor, status: "verified" } : factor));
      return route.fulfill({ headers: corsHeaders, json: session() });
    }
    const factorPath = path.match(/^\/factors\/([^/]+)$/);
    if (factorPath && method === "DELETE") {
      state.unenrolled.push(factorPath[1]);
      state.factors = state.factors.filter((factor) => factor.id !== factorPath[1]);
      return route.fulfill({ headers: corsHeaders, json: { id: factorPath[1] } });
    }
    return route.fulfill({ status: 404, headers: corsHeaders, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await mockCatalogs(page);
  await page.route("**/api/chats/unread", async (route) => route.fulfill({ headers: corsHeaders, json: { total: 0 } }));
  const account = () => ({
    user_id: "account-phone-1", role: "client", profile_id: null,
    first_name: "Camila", last_name: "Rojas", national_id: "12345678-5", phone: state.phone,
  });
  await page.route("**/api/account/me", async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });
    return route.fulfill({ headers: corsHeaders, json: account() });
  });
  await page.route("**/api/account/phone", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });
    const body = request.postDataJSON() as Record<string, unknown>;
    state.phonePuts.push(body);
    if (options.phoneAnswer) return route.fulfill({ status: options.phoneAnswer.status, headers: corsHeaders, json: options.phoneAnswer.json });
    state.phone = String(body.phone);
    return route.fulfill({ headers: corsHeaders, json: account() });
  });
  return state;
}

async function openProfile(page: Page) {
  const tokenRequest = page.waitForRequest((request) => request.url().includes("/auth/v1/token") && request.method() === "POST");
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await tokenRequest;
  await page.goto("/cuenta/perfil");
}

const main = (page: Page) => page.getByRole("main");
const field = (page: Page, term: string) => main(page).locator(".account-data > div").filter({ has: page.locator("dt", { hasText: new RegExp(`^${term}$`) }) }).locator("dd");

test("the profile shows the name, last name, RUT, email and phone, without the account type", async ({ page }) => {
  await installMocks(page);
  await openProfile(page);

  await expect(field(page, "Nombre")).toHaveText("Camila");
  await expect(field(page, "Apellido")).toHaveText("Rojas");
  await expect(field(page, "RUT")).toHaveText("12345678-5");
  await expect(field(page, "Correo")).toHaveText("camila@example.test");
  await expect(field(page, "Teléfono")).toContainText(OLD_PHONE);
  await expect(main(page).getByText("Tipo de cuenta")).toHaveCount(0);
  await expect(main(page).getByText("No registrado")).toHaveCount(0);
});

test("a user changes the phone with the SMS code, and the old SMS factor is removed", async ({ page }) => {
  const state = await installMocks(page);
  await openProfile(page);

  await main(page).getByRole("button", { name: "Cambiar teléfono" }).click();
  await main(page).getByLabel("Número nuevo").fill("+56 9 2222 2222");
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await expect(main(page).getByText(`Enviamos un código a ${NEW_PHONE}.`)).toBeVisible();
  await main(page).getByLabel("Código SMS").fill(SMS_CODE);
  await main(page).getByRole("button", { name: "Confirmar número" }).click();

  await expect(main(page).getByRole("status")).toHaveText("Tu número de teléfono se actualizó.");
  await expect(field(page, "Teléfono")).toContainText(NEW_PHONE);
  expect(state.enrollBodies).toEqual([expect.objectContaining({ factor_type: "phone", phone: NEW_PHONE })]);
  expect(state.phonePuts).toEqual([{ factor_id: "factor-new", phone: NEW_PHONE }]);
  expect(state.unenrolled).toEqual(["factor-old"]);
});

test("a wrong SMS code is refused and the phone is not saved", async ({ page }) => {
  const state = await installMocks(page);
  await openProfile(page);

  await main(page).getByRole("button", { name: "Cambiar teléfono" }).click();
  await main(page).getByLabel("Número nuevo").fill(NEW_PHONE);
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await main(page).getByLabel("Código SMS").fill("000000");
  await main(page).getByRole("button", { name: "Confirmar número" }).click();

  await expect(main(page).locator(".auth-error")).toHaveText("El código no es válido o venció. Solicita otro código e inténtalo nuevamente.");
  expect(state.phonePuts).toEqual([]);
  expect(state.unenrolled).toEqual([]);
  await expect(field(page, "Teléfono")).toContainText(OLD_PHONE);
});

test("a local number or the current number is flagged and no SMS is sent", async ({ page }) => {
  const state = await installMocks(page);
  await openProfile(page);

  await main(page).getByRole("button", { name: "Cambiar teléfono" }).click();
  await main(page).getByLabel("Número nuevo").fill("922222222");
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await expect(main(page).locator(".auth-error")).toHaveText("Ingresa un número internacional con código de país, por ejemplo +56912345678.");
  await main(page).getByLabel("Número nuevo").fill(OLD_PHONE);
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await expect(main(page).locator(".auth-error")).toHaveText("Ese ya es tu número actual.");
  expect(state.enrollBodies).toEqual([]);
});

test("cancelling after the SMS was sent removes the unfinished factor", async ({ page }) => {
  const state = await installMocks(page);
  await openProfile(page);

  await main(page).getByRole("button", { name: "Cambiar teléfono" }).click();
  await main(page).getByLabel("Número nuevo").fill(NEW_PHONE);
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await expect(main(page).getByLabel("Código SMS")).toBeVisible();
  await main(page).getByRole("button", { name: "Cancelar" }).click();

  await expect(main(page).getByRole("button", { name: "Cambiar teléfono" })).toBeVisible();
  expect(state.unenrolled).toEqual(["factor-new"]);
  expect(state.phonePuts).toEqual([]);
});

test("the API's refusal is shown and the old SMS factor is kept", async ({ page }) => {
  const detail = "Verifica el número nuevo con el código SMS antes de guardarlo.";
  const state = await installMocks(page, { phoneAnswer: { status: 422, json: { detail } } });
  await openProfile(page);

  await main(page).getByRole("button", { name: "Cambiar teléfono" }).click();
  await main(page).getByLabel("Número nuevo").fill(NEW_PHONE);
  await main(page).getByRole("button", { name: "Enviar código" }).click();
  await main(page).getByLabel("Código SMS").fill(SMS_CODE);
  await main(page).getByRole("button", { name: "Confirmar número" }).click();

  await expect(main(page).locator(".auth-error")).toHaveText(detail);
  expect(state.unenrolled).toEqual([]);
  await expect(field(page, "Teléfono")).toContainText(OLD_PHONE);
});
