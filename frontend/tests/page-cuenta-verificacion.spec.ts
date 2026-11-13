import { expect, test, type Page, type Route } from "@playwright/test";

const user = {
  id: "driver-user-1",
  aud: "authenticated",
  role: "authenticated",
  email: "conductor@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const phoneFactor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
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

// Auth calls for the email/password, SMS MFA and session checks.
async function mockAuth(page: Page) {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const authPath = url.pathname.replace("/auth/v1", "");
    const method = request.method();

    if (authPath === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: session("aal1", "password-aal1-token") });
      return;
    }
    if (authPath === "/user" && method === "GET") {
      await route.fulfill({ json: { ...user, factors: [phoneFactor] } });
      return;
    }
    if (authPath === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: [phoneFactor], phone: [phoneFactor], totp: [] } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/challenge" && method === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/verify" && method === "POST") {
      await route.fulfill({ json: session("aal2", "verified-aal2-token") });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${authPath}` } });
  });
}

const verificationUrl = /\/api\/driver\/verifications$/;

type Status = "missing" | "verified" | "in_review" | "rejected";
type Certificate = { type: "criminal_record" | "driver_record"; status: Status; reason: string | null; submittedAt: string | null; verifiedAt: string | null };

function certificate(type: Certificate["type"], status: Status = "missing", reason: string | null = null): Certificate {
  return {
    type,
    status,
    reason,
    submittedAt: status === "missing" ? null : "2026-11-13T12:00:00.000Z",
    verifiedAt: status === "verified" ? "2026-11-13T12:00:00.000Z" : null,
  };
}

function view(criminal: Certificate, driver: Certificate) {
  return { verified: criminal.status === "verified" && driver.status === "verified", certificates: [criminal, driver] };
}

// Signs in through the real login form with MFA completed, landing on /cuenta/verificacion.
async function signInToVerification(page: Page) {
  await mockAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "independent_driver", profile_id: "solo-profile-1" } }));
  await page.goto("/login?next=%2Fcuenta%2Fverificacion");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/verificacion$/);
}

// Serves the verification state; each POST answers with the next state or a failure. Requests are recorded.
async function mockVerificationApi(
  page: Page,
  options: { initial?: ReturnType<typeof view>; getStatus?: number; getDetail?: string; answers?: Array<{ status: number; json: unknown }> } = {},
) {
  let current = options.initial ?? view(certificate("criminal_record"), certificate("driver_record"));
  const answers = [...(options.answers ?? [])];
  const posts: unknown[] = [];
  await page.route(verificationUrl, async (route: Route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.method() === "GET") {
      if (options.getStatus) {
        await route.fulfill({ status: options.getStatus, headers: corsHeaders, json: { detail: options.getDetail ?? "" } });
        return;
      }
      await route.fulfill({ headers: corsHeaders, json: current });
      return;
    }
    posts.push(request.postDataJSON());
    const answer = answers.shift() ?? { status: 500, json: {} };
    if (answer.status === 201) current = answer.json as typeof current;
    await route.fulfill({ status: answer.status, headers: corsHeaders, json: answer.json });
  });
  return { posts };
}

const criminalForm = (page: Page) => page.getByRole("form", { name: "Verificar certificado de antecedentes" });
const driverForm = (page: Page) => page.getByRole("form", { name: "Verificar hoja de vida del conductor" });

test.describe("cuenta verificacion", () => {
  test("a driver verifies both certificates by folio and verification code", async ({ page }) => {
    const verifiedCriminal = view(certificate("criminal_record", "verified"), certificate("driver_record"));
    const { posts } = await mockVerificationApi(page, {
      answers: [
        { status: 201, json: verifiedCriminal },
        { status: 201, json: view(certificate("criminal_record", "verified"), certificate("driver_record", "verified")) },
      ],
    });
    await signInToVerification(page);

    await expect(page.getByRole("heading", { name: "Certificados del conductor" })).toBeVisible();
    await expect(page.getByText("Mientras tus dos certificados no estén verificados")).toBeVisible();
    await criminalForm(page).getByLabel("Folio").fill(" 50070080804 ");
    await criminalForm(page).getByLabel("Código verificador").fill("2aacbb9a636a");
    await criminalForm(page).getByRole("button", { name: "Verificar certificado" }).click();

    await expect(page.getByRole("status")).toHaveText("Certificado verificado.");
    await expect(criminalForm(page)).toHaveCount(0);
    await driverForm(page).getByLabel("Folio").fill("50070080805");
    await driverForm(page).getByLabel("Código verificador").fill("abc123");
    await driverForm(page).getByRole("button", { name: "Verificar certificado" }).click();

    await expect(page.getByText("Tus certificados están verificados.")).toBeVisible();
    expect(posts).toEqual([
      { type: "criminal_record", folio: "50070080804", verification_code: "2aacbb9a636a" },
      { type: "driver_record", folio: "50070080805", verification_code: "abc123" },
    ]);
  });

  test("an invalid folio is flagged inline and nothing is sent", async ({ page }) => {
    const { posts } = await mockVerificationApi(page);
    await signInToVerification(page);

    await criminalForm(page).getByLabel("Folio").fill("123");
    await criminalForm(page).getByRole("button", { name: "Verificar certificado" }).click();

    await expect(criminalForm(page).getByText("El folio tiene entre 10 y 15 letras o números.")).toBeVisible();
    await expect(criminalForm(page).getByText("Ingresa el código verificador.")).toBeVisible();
    expect(posts).toEqual([]);
  });

  test("a certificate with annotations shows it is in review", async ({ page }) => {
    const reason = "El certificado tiene anotaciones y será revisado por el equipo de Amira.";
    await mockVerificationApi(page, {
      answers: [{ status: 201, json: view(certificate("criminal_record", "in_review", reason), certificate("driver_record")) }],
    });
    await signInToVerification(page);

    await criminalForm(page).getByLabel("Folio").fill("50070080804");
    await criminalForm(page).getByLabel("Código verificador").fill("2aacbb9a636a");
    await criminalForm(page).getByRole("button", { name: "Verificar certificado" }).click();

    await expect(page.getByRole("status")).toHaveText("Recibimos tu certificado. El equipo de Amira lo revisará.");
    await expect(page.getByText("En revisión")).toBeVisible();
    await expect(page.getByText(reason)).toBeVisible();
    await expect(criminalForm(page)).toHaveCount(0);
  });

  test("a rejected certificate shows the reason and can be sent again", async ({ page }) => {
    await mockVerificationApi(page, {
      initial: view(certificate("criminal_record", "rejected", "El certificado pertenece a otra persona."), certificate("driver_record")),
    });
    await signInToVerification(page);

    await expect(page.getByText("Rechazado")).toBeVisible();
    await expect(page.getByText("El certificado pertenece a otra persona.")).toBeVisible();
    await expect(criminalForm(page)).toBeVisible();
  });

  test("the API's Spanish detail is shown when a certificate is refused", async ({ page }) => {
    await mockVerificationApi(page, { answers: [{ status: 409, json: { detail: "Este certificado ya fue usado en Amira." } }] });
    await signInToVerification(page);

    await criminalForm(page).getByLabel("Folio").fill("50070080804");
    await criminalForm(page).getByLabel("Código verificador").fill("2aacbb9a636a");
    await criminalForm(page).getByRole("button", { name: "Verificar certificado" }).click();

    await expect(page.locator(".auth-error")).toHaveText("Este certificado ya fue usado en Amira.");
    await expect(criminalForm(page).getByLabel("Folio")).toHaveValue("50070080804");
  });

  test("an account that is not a driver is told so", async ({ page }) => {
    await mockVerificationApi(page, { getStatus: 403, getDetail: "Solo los conductores pueden verificar certificados." });
    await signInToVerification(page);

    await expect(page.locator(".auth-error")).toHaveText("Solo los conductores pueden verificar certificados.");
  });
});
