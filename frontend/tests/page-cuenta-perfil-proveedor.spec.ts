import { expect, test, type Page, type Request } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
};

const user = {
  id: "user-profile-1",
  aud: "authenticated",
  role: "authenticated",
  email: "persona@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

type Role = "independent_driver" | "company_owner" | "company_driver" | "client";
type ProfileBody = {
  name: string;
  kind: string;
  description: string | null;
  commune_code: string | null;
  service_type_ids: string[];
  published: boolean;
  missing: string[];
};

// The profile page reads the session, so the fake session must be AAL2 (SMS-verified), as on the other private pages.
function accessToken() {
  const payload = Buffer.from(JSON.stringify({ aal: "aal2", exp: 2000000000, sub: user.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.profile-access-token`;
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

const completeProfile: ProfileBody = {
  name: "Conductor Demo",
  kind: "independent_driver",
  description: "Mudanzas en Santiago con camioneta.",
  commune_code: "13101",
  service_type_ids: ["service-type-1"],
  published: false,
  missing: [],
};

// Company owners are stored with kind "company"; only they can set a name.
const companyProfile: ProfileBody = { ...completeProfile, kind: "company" };

// The backend returns a null description for a profile that never saved one.
const incompleteProfile: ProfileBody = {
  ...completeProfile,
  description: null,
  commune_code: null,
  service_type_ids: [],
  missing: ["description", "commune", "service_types"],
};

// Mirrors the backend's missing-item rules, in its order, so the saved profile reports its own checklist.
function missingFor(profile: ProfileBody) {
  const missing: string[] = [];
  if (!profile.description?.trim()) missing.push("description");
  if (!profile.commune_code) missing.push("commune");
  if (profile.service_type_ids.length === 0) missing.push("service_types");
  return missing;
}

// Rejection bodies are the exact JSON the backend's provider profile routes return on 422.
type MockOptions = {
  role: Role | null;
  profile?: ProfileBody;
  saveRejection?: { detail: unknown };
  publishRejection?: { detail: unknown };
};

// Fake Supabase Auth, account role, catalogs, and a stateful provider profile API. Returns the request log the tests assert on.
async function installProfileMocks(page: Page, options: MockOptions) {
  const state = {
    profile: { ...(options.profile ?? completeProfile) },
    putBodies: [] as Array<Record<string, unknown>>,
    // Ordered log of provider profile calls, so tests can assert that a save precedes a publish.
    calls: [] as string[],
    publishCalls: 0,
    unpublishCalls: 0,
    // Counts profile reads, so tests can assert that the page refetched the saved profile.
    getCalls: 0,
  };

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
      await route.fulfill({ headers: corsHeaders, json: session() });
      return;
    }
    if (path === "/user" && method === "GET") {
      await route.fulfill({ headers: corsHeaders, json: { ...user, factors: [] } });
      return;
    }
    await route.fulfill({ status: 404, headers: corsHeaders, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });

  await mockCatalogs(page);
  await page.route("**/api/chats/unread", async (route) => route.fulfill({ headers: corsHeaders, json: { total: 0 } }));
  await page.route("**/api/account/me", async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });
    return route.fulfill({ headers: corsHeaders, json: { user_id: "account-profile-1", role: options.role, profile_id: null } });
  });

  await page.route("**/api/provider/profile**", async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;

    if (method === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });
    if (method === "GET") {
      state.getCalls += 1;
      return route.fulfill({ headers: corsHeaders, json: state.profile });
    }
    state.calls.push(`${method} ${path}`);

    if (method === "PUT") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.putBodies.push(body);
      if (options.saveRejection) {
        return route.fulfill({ status: 422, headers: corsHeaders, json: options.saveRejection });
      }
      state.profile = {
        ...state.profile,
        description: body.description as string,
        commune_code: body.commune_code as string | null,
        service_type_ids: body.service_type_ids as string[],
        ...(typeof body.name === "string" ? { name: body.name } : {}),
      };
      state.profile.missing = missingFor(state.profile);
      // Backend rule: a PUT that leaves a published profile incomplete unpublishes it.
      if (state.profile.published && state.profile.missing.length > 0) state.profile.published = false;
      return route.fulfill({ headers: corsHeaders, json: state.profile });
    }

    if (path.endsWith("/publish")) {
      state.publishCalls += 1;
      if (options.publishRejection) {
        return route.fulfill({ status: 422, headers: corsHeaders, json: options.publishRejection });
      }
      state.profile = { ...state.profile, published: true };
      return route.fulfill({ headers: corsHeaders, json: state.profile });
    }

    if (path.endsWith("/unpublish")) {
      state.unpublishCalls += 1;
      state.profile = { ...state.profile, published: false };
      return route.fulfill({ headers: corsHeaders, json: state.profile });
    }

    return route.fulfill({ status: 404, headers: corsHeaders, json: { detail: "Unexpected provider profile request" } });
  });

  return state;
}

// Signs in through the real login form so the Supabase client stores the session the profile page reads.
async function signIn(page: Page) {
  const tokenRequest = page.waitForRequest((request) => request.url().includes("/auth/v1/token") && request.method() === "POST");
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await tokenRequest;
}

// Scoped to <main> so header links do not collide with the form controls.
const main = (page: Page) => page.getByRole("main");

test("independent driver edits the profile and the saved PUT body matches the form", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "independent_driver", profile: incompleteProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByRole("heading", { name: "Perfil público" })).toBeVisible();
  await main(page).getByLabel("Descripción").fill("Mudanzas con camioneta y ayudantes.");
  await main(page).getByLabel("Comuna").selectOption("13114");
  await main(page).getByRole("checkbox", { name: "Mudanzas", exact: true }).check();

  const saveRequest = page.waitForRequest((request: Request) => request.url().includes("/api/provider/profile") && request.method() === "PUT");
  await main(page).getByRole("button", { name: "Guardar" }).click();
  const request = await saveRequest;

  expect(request.postDataJSON()).toEqual({
    description: "Mudanzas con camioneta y ayudantes.",
    commune_code: "13114",
    service_type_ids: ["service-type-1"],
  });
  await expect(main(page).getByText("Cambios guardados.")).toBeVisible();
  expect(state.putBodies).toHaveLength(1);
});

test("missing checklist is shown while the profile is incomplete", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: incompleteProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByText("Falta para publicar tu perfil:")).toBeVisible();
  await expect(main(page).getByRole("listitem")).toHaveText([
    "Escribe una descripción",
    "Elige tu comuna",
    "Elige al menos un tipo de servicio",
  ]);
  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
});

test("a null description from the backend renders as an empty textarea", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: incompleteProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByLabel("Descripción")).toHaveValue("");
  await expect(main(page).getByText("null")).toHaveCount(0);
});

test("publish saves unsaved edits first (PUT) and then publishes (POST), with the edited body", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "independent_driver", profile: completeProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByLabel("Descripción").fill("Mudanzas con camioneta y ayudantes.");
  await main(page).getByRole("button", { name: "Publicar perfil" }).click();

  await expect(main(page).getByText("Tu perfil está publicado y aparece cuando un usuario busca un servicio.")).toBeVisible();
  expect(state.calls).toEqual(["PUT /api/provider/profile", "POST /api/provider/profile/publish"]);
  expect(state.putBodies[0]).toEqual({
    description: "Mudanzas con camioneta y ayudantes.",
    commune_code: "13101",
    service_type_ids: ["service-type-1"],
  });
});

test("a publish that fails after the save still refetches the saved profile and shows the publish error", async ({ page }) => {
  const state = await installProfileMocks(page, {
    role: "independent_driver",
    profile: incompleteProfile,
    publishRejection: { detail: { message: "Profile is incomplete.", missing: ["service_types"] } },
  });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByLabel("Descripción").fill("Mudanzas con camioneta y ayudantes.");
  await main(page).getByLabel("Comuna").selectOption("13101");
  await main(page).getByRole("checkbox", { name: "Mudanzas", exact: true }).check();
  const readsBeforePublish = state.getCalls;
  await main(page).getByRole("button", { name: "Publicar perfil" }).click();

  await expect(main(page).getByRole("alert")).toHaveText("Para publicar tu perfil falta: Elige al menos un tipo de servicio.");
  expect(state.calls).toEqual(["PUT /api/provider/profile", "POST /api/provider/profile/publish"]);
  expect(state.getCalls).toBeGreaterThan(readsBeforePublish);
  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
});

test("a failed save does not publish and shows the save error", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "independent_driver", profile: completeProfile, saveRejection: { detail: "Unknown commune." } });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByRole("button", { name: "Publicar perfil" }).click();

  await expect(main(page).getByRole("alert")).toHaveText("La comuna elegida no existe.");
  expect(state.calls).toEqual(["PUT /api/provider/profile"]);
  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
});

test("publish is disabled while the form is incomplete and enabled once it is filled", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: incompleteProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  const publish = main(page).getByRole("button", { name: "Publicar perfil" });
  await expect(publish).toBeDisabled();

  await main(page).getByLabel("Descripción").fill("Mudanzas con camioneta.");
  await expect(publish).toBeDisabled();
  await main(page).getByLabel("Comuna").selectOption("13101");
  await expect(publish).toBeDisabled();
  await main(page).getByRole("checkbox", { name: "Mudanzas", exact: true }).check();
  await expect(publish).toBeEnabled();
});

test("the checklist follows the form, not the saved profile", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: incompleteProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByLabel("Descripción").fill("Mudanzas con camioneta.");
  await expect(main(page).getByRole("listitem")).toHaveText(["Elige tu comuna", "Elige al menos un tipo de servicio"]);
});

test("company owner cannot publish with a blank company name", async ({ page }) => {
  await installProfileMocks(page, { role: "company_owner", profile: { ...companyProfile, name: "" } });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByRole("button", { name: "Publicar perfil" })).toBeDisabled();
  await expect(main(page).getByRole("listitem")).toHaveText(["Escribe el nombre de la empresa"]);
});

test("a save that unpublishes a published profile says so", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "independent_driver", profile: { ...completeProfile, published: true } });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByText("Tu perfil está publicado y aparece cuando un usuario busca un servicio.")).toBeVisible();
  await main(page).getByLabel("Comuna").selectOption("");
  await main(page).getByRole("button", { name: "Guardar" }).click();

  await expect(main(page).getByText("Tu perfil dejó de ser público porque le faltan datos.")).toBeVisible();
  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
  expect(state.putBodies).toHaveLength(1);
});

test("publish sends POST publish and the status changes to published", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "independent_driver" });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
  const publishRequest = page.waitForRequest((request: Request) => request.url().includes("/api/provider/profile/publish") && request.method() === "POST");
  await main(page).getByRole("button", { name: "Publicar perfil" }).click();
  await publishRequest;

  await expect(main(page).getByText("Tu perfil está publicado y aparece cuando un usuario busca un servicio.")).toBeVisible();
  await expect(main(page).getByRole("button", { name: "Ocultar perfil" })).toBeVisible();
  expect(state.publishCalls).toBe(1);
});

test("a 422 on publish lists the missing items in Spanish, never the English backend message", async ({ page }) => {
  await installProfileMocks(page, {
    role: "independent_driver",
    profile: completeProfile,
    publishRejection: { detail: { message: "Profile is incomplete.", missing: ["service_types", "commune"] } },
  });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByRole("button", { name: "Publicar perfil" }).click();

  await expect(main(page).getByRole("alert")).toHaveText("Para publicar tu perfil falta: Elige al menos un tipo de servicio, Elige tu comuna.");
  await expect(main(page).getByText("Profile is incomplete.")).toHaveCount(0);
  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
});

test("a 422 on save maps the backend's unknown commune to Spanish copy", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: completeProfile, saveRejection: { detail: "Unknown commune." } });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await main(page).getByRole("button", { name: "Guardar" }).click();

  await expect(main(page).getByRole("alert")).toHaveText("La comuna elegida no existe.");
  await expect(main(page).getByText("Unknown commune.")).toHaveCount(0);
});

test("unpublish sends POST unpublish and the status changes to unpublished", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "company_owner", profile: { ...companyProfile, published: true } });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByText("Tu perfil está publicado y aparece cuando un usuario busca un servicio.")).toBeVisible();
  const unpublishRequest = page.waitForRequest((request: Request) => request.url().includes("/api/provider/profile/unpublish") && request.method() === "POST");
  await main(page).getByRole("button", { name: "Ocultar perfil" }).click();
  await unpublishRequest;

  await expect(main(page).getByText("Tu perfil no está publicado.")).toBeVisible();
  await expect(main(page).getByRole("button", { name: "Publicar perfil" })).toBeVisible();
  expect(state.unpublishCalls).toBe(1);
});

test("company owner sees the company name field and saves it", async ({ page }) => {
  const state = await installProfileMocks(page, { role: "company_owner", profile: companyProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByLabel("Nombre de la empresa")).toHaveValue("Conductor Demo");
  await main(page).getByLabel("Nombre de la empresa").fill("Mudanzas Demo SpA");
  const saveRequest = page.waitForRequest((request: Request) => request.url().includes("/api/provider/profile") && request.method() === "PUT");
  await main(page).getByRole("button", { name: "Guardar" }).click();

  expect((await saveRequest).postDataJSON()).toMatchObject({ name: "Mudanzas Demo SpA" });
  await expect(main(page).getByText("Cambios guardados.")).toBeVisible();
  expect(state.putBodies).toHaveLength(1);
});

test("independent driver does not see the company name field", async ({ page }) => {
  await installProfileMocks(page, { role: "independent_driver", profile: completeProfile });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByRole("heading", { name: "Perfil público" })).toBeVisible();
  await expect(main(page).getByLabel("Nombre de la empresa")).toHaveCount(0);
});

test("client keeps the read-only view without the provider form", async ({ page }) => {
  await installProfileMocks(page, { role: "client" });
  await signIn(page);
  await page.goto("/cuenta/perfil");
  await expect(main(page).getByText("Cliente")).toBeVisible();
  await expect(main(page).getByRole("heading", { name: "Perfil público" })).toHaveCount(0);
  await expect(main(page).getByRole("button", { name: "Guardar" })).toHaveCount(0);
});

test("company driver does not see the provider form", async ({ page }) => {
  await installProfileMocks(page, { role: "company_driver" });
  await signIn(page);
  await page.goto("/cuenta/perfil");

  await expect(main(page).getByText("Conductor de empresa")).toBeVisible();
  await expect(main(page).getByRole("heading", { name: "Perfil público" })).toHaveCount(0);
  await expect(main(page).getByRole("button", { name: "Publicar perfil" })).toHaveCount(0);
});
