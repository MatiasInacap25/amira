import { expect, test, type Page, type Route } from "@playwright/test";
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

// 1x1 PNG, enough for the browser to decode a delivery photo preview or a signed link.
const PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

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

function inHours(hours: number) {
  return new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
}

// Only the auth calls the login and MFA steps need. Mirrors the sign-in flow used in page-cuenta-servicios.spec.ts.
async function mockSmsVerifiedAuth(page: Page) {
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
}

// Signs in through the real login form. The list page it lands on is answered empty so only the detail page is under test.
async function signInTo(page: Page, role: string) {
  await mockSmsVerifiedAuth(page);
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-test-1", role, profile_id: null } }));
  await page.route("**/api/customer/services?*", async (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route("**/api/provider/services?*", async (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.goto("/login?next=%2Fcuenta%2Fservicios");
  await page.locator("#auth-email").fill("persona@example.test");
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/servicios$/);
}

function serviceDetail(overrides: Record<string, unknown> = {}) {
  return {
    serviceId: "service-1",
    status: "completed",
    serviceTypeName: "Mudanzas",
    serviceAt: "2026-10-20T13:00:00Z",
    amount: 45000,
    currency: "CLP",
    originCommune: "Santiago",
    destinationCommune: "Valparaíso",
    isExclusive: false,
    counterpartName: "Transportes Andes",
    assignmentCount: 1,
    chatId: "chat-1",
    description: "Mudanza de dos habitaciones con piano.",
    createdAt: "2026-10-01T10:00:00Z",
    startedAt: "2026-10-20T13:05:00Z",
    completedAt: "2026-10-20T16:00:00Z",
    payoutDeadlineAt: inHours(3),
    viewerRole: "customer",
    canManage: false,
    viewerAssigned: false,
    assignments: [
      { driverId: "driver-1", driverFirstName: "Lucía", vehicleId: "vehicle-1", vehicleLabel: "Furgón 3,5 t", plate: "KLM12" },
    ],
    deliveryPhotoAvailable: false,
    customerConsentAt: null,
    claimOpen: false,
    canClaim: true,
    canConsent: true,
    ...overrides,
  };
}

// Answers GET /api/{viewer}/services/service-1 with the handler. Only the detail route is matched, not the list.
async function mockServiceDetail(page: Page, viewer: "customer" | "provider", respond: (route: Route) => Promise<void>) {
  const requests: string[] = [];
  await page.route(`**/api/${viewer}/services/service-1`, async (route) => {
    requests.push(route.request().method());
    await respond(route);
  });
  return requests;
}

test("signed-out visitor sees a sign-in prompt and the detail is never requested", async ({ page }) => {
  const requests = await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail() }));

  await page.goto("/cuenta/servicios/service-1");

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "No pudimos verificar tu sesión" })).toBeVisible();
  await expect(alert.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fcuenta%2Fservicios");
  expect(requests).toHaveLength(0);
});

test("unknown service shows the not-found state with a link back to the list", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ status: 404, json: { detail: "Not found" } }));
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  const empty = page.locator(".customer-services-wrap .marketplace-empty");
  await expect(empty.getByRole("heading", { name: "Servicio no encontrado" })).toBeVisible();
  await expect(empty.getByText("Este servicio no existe o no está disponible en tu cuenta.", { exact: true })).toBeVisible();
  await expect(empty.getByRole("link", { name: "Volver a mis servicios" })).toHaveAttribute("href", "/cuenta/servicios");
});

test("a failed detail request shows a retryable error that recovers the service", async ({ page }) => {
  let attempts = 0;
  await mockServiceDetail(page, "customer", async (route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 500, json: { detail: "Internal error" } });
    else await route.fulfill({ json: serviceDetail() });
  });
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  const alert = page.locator(".customer-services-wrap [role=alert]");
  await expect(alert.getByRole("heading", { name: "No pudimos cargar este servicio" })).toBeVisible();
  await expect(page.locator(".account-service-detail")).toHaveCount(0);

  await alert.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Mudanzas" })).toBeVisible();
  await expect(page.locator(".customer-services-wrap [role=alert]")).toHaveCount(0);
});

test("customer sees the counterpart, route, amount, dates, description and a chat link", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail() }));
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  const detail = page.locator(".account-service-detail");
  await expect(detail.getByRole("heading", { level: 1, name: "Mudanzas" })).toBeVisible();
  await expect(detail.getByText("Prestador: Transportes Andes", { exact: true })).toBeVisible();
  await expect(detail.locator(".account-service-status")).toHaveText("Finalizado");

  const fact = (label: string) => detail.locator(".account-service-detail-facts > div", { has: page.locator("dt", { hasText: label }) }).locator("dd");
  await expect(fact("Ruta")).toHaveText("Santiago → Valparaíso");
  await expect(fact("Monto")).toHaveText("$45.000");
  await expect(fact("Exclusivo")).toHaveText("No");
  await expect(fact("Finalizado")).toHaveText(/20-10-2026, 1:00/);
  await expect(detail.getByRole("heading", { name: "Descripción" })).toBeVisible();
  await expect(detail.getByText("Mudanza de dos habitaciones con piano.", { exact: true })).toBeVisible();

  await expect(page.getByRole("link", { name: "Volver a mis servicios" })).toHaveAttribute("href", "/cuenta/servicios");
  await expect(page.getByRole("link", { name: "Abrir conversación" })).toHaveAttribute("href", "/mensajes/chat-1");
});

test("customer sees each assigned driver with vehicle and plate, or an empty note", async ({ page }) => {
  let assignments: unknown[] = serviceDetail().assignments;
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail({ assignments }) }));
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Conductores asignados" }) });
  const driver = section.locator("li").filter({ hasText: "Lucía" });
  await expect(driver.getByText("Lucía", { exact: true })).toBeVisible();
  await expect(driver.getByText("Furgón 3,5 t", { exact: true })).toBeVisible();
  await expect(driver.getByText("KLM12", { exact: true })).toBeVisible();

  assignments = [];
  await page.reload();
  await expect(section.getByText("Aún no hay conductores asignados", { exact: true })).toBeVisible();
});

test("completed service without a chat hides the conversation link", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail({ chatId: null }) }));
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.getByRole("heading", { level: 1, name: "Mudanzas" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Abrir conversación" })).toHaveCount(0);
});

test("customer confirms consent after a confirmation step and the service records it", async ({ page }) => {
  let consented = false;
  const consentRequests: string[] = [];
  await mockServiceDetail(page, "customer", async (route) => {
    const consentedAt = "2026-10-18T15:00:00Z";
    await route.fulfill({
      json: serviceDetail({
        customerConsentAt: consented ? consentedAt : null,
        canConsent: !consented,
        canClaim: !consented,
      }),
    });
  });
  await page.route("**/api/customer/services/service-1/consent", async (route) => {
    consentRequests.push(route.request().method());
    consented = true;
    await route.fulfill({
      json: serviceDetail({ customerConsentAt: "2026-10-18T15:00:00Z", canConsent: false, canClaim: false }),
    });
  });
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  await page.getByRole("button", { name: "Todo conforme" }).click();

  const confirm = page.locator("section", { has: page.getByRole("heading", { name: "Confirmar conformidad" }) });
  await expect(confirm.getByText("Al confirmar, el pago al prestador se libera antes del plazo. Después no podrás reclamar este servicio.", { exact: true })).toBeVisible();
  expect(consentRequests).toHaveLength(0);

  await confirm.getByRole("button", { name: "Confirmar conformidad" }).click();

  await expect(page.getByText("Registramos tu conformidad. El pago al prestador se liberará en el próximo proceso.", { exact: true })).toBeVisible();
  await expect(page.locator(".account-service-state-consent")).toBeVisible();
  await expect(page.getByRole("button", { name: "Todo conforme" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reclamar" })).toHaveCount(0);
  expect(consentRequests).toEqual(["POST"]);
});

test("cancelling the consent confirmation sends nothing and restores the actions", async ({ page }) => {
  const consentRequests: string[] = [];
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail() }));
  await page.route("**/api/customer/services/service-1/consent", async (route) => {
    consentRequests.push(route.request().method());
    await route.fulfill({ status: 500, json: { detail: "Should not be called" } });
  });
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  await page.getByRole("button", { name: "Todo conforme" }).click();
  await page.locator("section", { has: page.getByRole("heading", { name: "Confirmar conformidad" }) })
    .getByRole("button", { name: "Cancelar" })
    .click();

  await expect(page.getByRole("button", { name: "Todo conforme" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Todo conforme" })).toBeFocused();
  expect(consentRequests).toHaveLength(0);
});

test("claim form rejects a blank reason, then sends the trimmed reason after confirmation", async ({ page }) => {
  const claimBodies: unknown[] = [];
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail() }));
  await page.route("**/api/customer/services/service-1/claims", async (route) => {
    claimBodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: serviceDetail({ claimOpen: true, status: "disputed", canClaim: false, canConsent: false }) });
  });
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  await page.getByRole("button", { name: "Reclamar" }).click();

  const form = page.locator("section", { has: page.getByRole("heading", { name: "Reclamar el servicio" }) });
  await form.getByRole("button", { name: "Continuar" }).click();
  await expect(form.getByRole("alert")).toHaveText("Escribe el motivo del reclamo.");
  expect(claimBodies).toHaveLength(0);

  await form.getByLabel("Motivo del reclamo (obligatorio)").fill("   ");
  await form.getByRole("button", { name: "Continuar" }).click();
  await expect(form.getByRole("alert")).toHaveText("Escribe el motivo del reclamo.");

  await form.getByLabel("Motivo del reclamo (obligatorio)").fill("  La carga llegó con un mueble roto.  ");
  await form.getByRole("button", { name: "Continuar" }).click();

  const confirm = page.locator("section", { has: page.getByRole("heading", { name: "Confirmar reclamo" }) });
  await expect(confirm.locator("blockquote")).toHaveText("La carga llegó con un mueble roto.");
  await confirm.getByRole("button", { name: "Enviar reclamo" }).click();

  await expect(page.getByText("Reclamo enviado. El pago al prestador queda retenido mientras se revisa.", { exact: true })).toBeVisible();
  expect(claimBodies).toEqual([{ reason: "La carga llegó con un mueble roto." }]);
});

test("a claim refused because the window closed returns to the actions and keeps the typed reason", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail() }));
  await page.route("**/api/customer/services/service-1/claims", async (route) =>
    route.fulfill({ status: 409, json: { detail: "The claim window for this service has closed." } }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  await page.getByRole("button", { name: "Reclamar" }).click();
  await page.getByLabel("Motivo del reclamo (obligatorio)").fill("Falta una caja.");
  await page.getByRole("button", { name: "Continuar" }).click();
  await page.locator("section", { has: page.getByRole("heading", { name: "Confirmar reclamo" }) })
    .getByRole("button", { name: "Enviar reclamo" })
    .click();

  const resolution = page.locator(".account-service-resolution");
  await expect(resolution.getByRole("alert")).toHaveText("El plazo para reclamar este servicio ya venció.");
  await expect(resolution.getByRole("button", { name: "Reclamar" })).toBeVisible();

  await resolution.getByRole("button", { name: "Reclamar" }).click();
  await expect(page.getByLabel("Motivo del reclamo (obligatorio)")).toHaveValue("Falta una caja.");
});

test("a disputed service shows its open claim and no consent or claim actions", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) =>
    route.fulfill({ json: serviceDetail({ status: "disputed", claimOpen: true, canClaim: false, canConsent: false }) }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.locator(".account-service-status")).toHaveText("En reclamo");
  await expect(page.getByText("Reclamo abierto. El pago al prestador queda retenido mientras se revisa.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Conformidad y reclamo" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Todo conforme" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reclamar" })).toHaveCount(0);
});

test("a service already confirmed by the customer shows the consent date and no actions", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) =>
    route.fulfill({
      json: serviceDetail({ customerConsentAt: "2026-10-18T15:00:00Z", canConsent: false, canClaim: false }),
    }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.locator(".account-service-state-consent")).toContainText("Conformidad registrada el");
  await expect(page.getByRole("button", { name: "Todo conforme" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reclamar" })).toHaveCount(0);
});

test("customer delivery photo loads on request and shows the image", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail({ deliveryPhotoAvailable: true }) }));
  await page.route("**/api/customer/services/service-1/delivery-photo", async (route) =>
    route.fulfill({ json: { url: `data:image/png;base64,${PNG_BASE64}`, expiresAt: inHours(1) } }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  const photoSection = page.locator("section", { has: page.getByRole("heading", { name: "Foto de entrega" }) });
  await photoSection.getByRole("button", { name: "Ver foto de entrega" }).click();

  await expect(page.getByRole("img", { name: "Foto de entrega del servicio" })).toBeVisible();
  await expect(photoSection.getByRole("button", { name: "Recargar" })).toBeVisible();
});

test("delivery photo that is not uploaded yet explains it and offers no image", async ({ page }) => {
  await mockServiceDetail(page, "customer", async (route) => route.fulfill({ json: serviceDetail({ deliveryPhotoAvailable: true }) }));
  await page.route("**/api/customer/services/service-1/delivery-photo", async (route) =>
    route.fulfill({ status: 404, json: { detail: "Not found" } }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");
  const photoSection = page.locator("section", { has: page.getByRole("heading", { name: "Foto de entrega" }) });
  await photoSection.getByRole("button", { name: "Ver foto de entrega" }).click();

  await expect(photoSection.getByRole("alert")).toHaveText("Todavía no hay foto de entrega para este servicio.");
  await expect(page.getByRole("img", { name: "Foto de entrega del servicio" })).toHaveCount(0);
});

test("provider sees the client, the prefilled assignments, and a start action for a confirmed service", async ({ page }) => {
  let status = "confirmed";
  const startRequests: string[] = [];
  const optionsRequests: string[] = [];
  await mockServiceDetail(page, "provider", async (route) =>
    route.fulfill({
      json: serviceDetail({
        status,
        viewerRole: "provider",
        canManage: true,
        counterpartName: "Ana Pérez",
        completedAt: null,
        payoutDeadlineAt: null,
        canClaim: false,
        canConsent: false,
      }),
    }),
  );
  await page.route("**/api/provider/services/service-1/assignment-options", async (route) => {
    optionsRequests.push(route.request().method());
    await route.fulfill({
      json: {
        drivers: [{ driverId: "driver-1", firstName: "Lucía", lastName: "Soto", isOwner: true }],
        vehicles: [{ vehicleId: "vehicle-1", vehicleLabel: "Furgón 3,5 t", plate: "KLM12" }],
      },
    });
  });
  await page.route("**/api/provider/services/service-1/start", async (route) => {
    startRequests.push(route.request().method());
    status = "in_progress";
    await route.fulfill({ json: serviceDetail({ status, viewerRole: "provider", canManage: true, viewerAssigned: true, completedAt: null, payoutDeadlineAt: null }) });
  });
  await signInTo(page, "independent_driver");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.getByText("Cliente: Ana Pérez", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Conformidad y reclamo" })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "Conductor" })).toHaveValue("driver-1");
  await expect(page.getByRole("combobox", { name: "Vehículo" })).toHaveValue("vehicle-1");
  await expect(page.getByRole("button", { name: "Guardar asignaciones" })).toBeVisible();
  expect(optionsRequests.length).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Iniciar servicio" }).click();

  await expect(page.locator(".account-service-status")).toHaveText("En curso");
  await expect(page.getByRole("button", { name: "Iniciar servicio" })).toHaveCount(0);
  expect(startRequests).toEqual(["POST"]);
});

test("a confirmed service without assignments asks for a driver and vehicle before it can start", async ({ page }) => {
  await mockServiceDetail(page, "provider", async (route) =>
    route.fulfill({
      json: serviceDetail({
        status: "confirmed",
        viewerRole: "provider",
        canManage: true,
        assignments: [],
        assignmentCount: 0,
        completedAt: null,
        payoutDeadlineAt: null,
        canClaim: false,
        canConsent: false,
      }),
    }),
  );
  await page.route("**/api/provider/services/service-1/assignment-options", async (route) =>
    route.fulfill({
      json: {
        drivers: [{ driverId: "driver-1", firstName: "Lucía", lastName: "Soto", isOwner: true }],
        vehicles: [{ vehicleId: "vehicle-1", vehicleLabel: "Furgón 3,5 t", plate: "KLM12" }],
      },
    }),
  );
  await signInTo(page, "independent_driver");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.getByText("Asigna al menos un conductor y un vehículo para iniciar el servicio.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Iniciar servicio" })).toHaveCount(0);
});

test("assigned driver completes an in-progress service only after choosing a delivery photo", async ({ page }) => {
  let status = "in_progress";
  const completeRequests: string[] = [];
  await mockServiceDetail(page, "provider", async (route) =>
    route.fulfill({
      json: serviceDetail({
        status,
        viewerRole: "provider",
        canManage: false,
        viewerAssigned: true,
        counterpartName: "Ana Pérez",
        completedAt: null,
        payoutDeadlineAt: null,
        canClaim: false,
        canConsent: false,
      }),
    }),
  );
  await page.route("**/api/provider/services/service-1/complete", async (route) => {
    completeRequests.push(route.request().headers()["content-type"] ?? "");
    status = "completed";
    await route.fulfill({ json: serviceDetail({ status, viewerRole: "provider", viewerAssigned: true, counterpartName: "Ana Pérez", payoutDeadlineAt: null, canClaim: false, canConsent: false }) });
  });
  await signInTo(page, "independent_driver");

  await page.goto("/cuenta/servicios/service-1");

  const finish = page.getByRole("button", { name: "Finalizar servicio" });
  await expect(finish).toBeDisabled();
  await expect(page.getByLabel("Foto de entrega")).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");

  await page.getByLabel("Foto de entrega").setInputFiles({ name: "entrega.png", mimeType: "image/png", buffer: Buffer.from(PNG_BASE64, "base64") });
  await expect(finish).toBeEnabled();
  await expect(page.getByRole("img", { name: "Vista previa de la foto de entrega seleccionada" })).toBeVisible();

  await finish.click();

  await expect(page.locator(".account-service-status")).toHaveText("Finalizado");
  await expect(page.getByRole("button", { name: "Finalizar servicio" })).toHaveCount(0);
  expect(completeRequests).toHaveLength(1);
  expect(completeRequests[0]).toContain("multipart/form-data");
});

test("a photo that is not JPEG, PNG or WebP is rejected before any upload", async ({ page }) => {
  let completeRequests = 0;
  await mockServiceDetail(page, "provider", async (route) =>
    route.fulfill({
      json: serviceDetail({
        status: "in_progress",
        viewerRole: "provider",
        viewerAssigned: true,
        completedAt: null,
        payoutDeadlineAt: null,
        canClaim: false,
        canConsent: false,
      }),
    }),
  );
  await page.route("**/api/provider/services/service-1/complete", async (route) => {
    completeRequests += 1;
    await route.fulfill({ status: 500, json: { detail: "Should not be called" } });
  });
  await signInTo(page, "independent_driver");

  await page.goto("/cuenta/servicios/service-1");
  await page.getByLabel("Foto de entrega").setInputFiles({ name: "notas.txt", mimeType: "text/plain", buffer: Buffer.from("no es una foto") });

  const form = page.locator(".account-service-complete-form");
  await expect(form.getByRole("alert")).toHaveText("La foto debe ser JPEG, PNG o WebP.");
  await expect(page.getByRole("button", { name: "Finalizar servicio" })).toBeDisabled();
  expect(completeRequests).toBe(0);
});

test("service detail fits a phone-width viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockServiceDetail(page, "customer", async (route) =>
    route.fulfill({
      json: serviceDetail({
        description: "Mudanza de dos habitaciones con piano de cola, escaleras angostas y estacionamiento a más de cien metros del edificio de destino.",
        status: "disputed",
        claimOpen: true,
        canClaim: false,
        canConsent: false,
      }),
    }),
  );
  await signInTo(page, "client");

  await page.goto("/cuenta/servicios/service-1");

  await expect(page.getByRole("heading", { level: 1, name: "Mudanzas" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
