import { expect, test, type BrowserContext } from "@playwright/test";

for (const path of ["/admin", "/admin/auditoria"]) {
  test(`sign-in is required for ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin$|\/login\?next=\/admin$/);
  });
}


const authOrigin = `http://127.0.0.1:${process.env.AMIRA_TEST_AUTH_PORT ?? "54329"}`;
const appOrigin = `http://127.0.0.1:${process.env.AMIRA_TEST_APP_PORT ?? "3179"}`;

async function login(context: BrowserContext, admin: boolean) {
  const response = await context.request.get(`${authOrigin}/__admin_session?admin=${admin}`);
  const value = Buffer.from(JSON.stringify(await response.json())).toString("base64url");
  await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${value}`, url: appOrigin }]);
}

test("a signed-in non-admin sees the server-side denial", async ({ page, context }) => {
  await login(context, false);
  await page.goto("/admin/auditoria");
  await expect(page.getByRole("heading", { name: "No tienes acceso al panel de administración." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("audit filters reach the backend and results link to their entity", async ({ page, context }) => {
  await login(context, true);
  await page.goto("/admin/auditoria");
  await page.getByLabel("Acción").fill("rating.hide");
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page).toHaveURL(/action=rating.hide/);
  await expect(page.getByRole("cell", { name: "rating.hide" })).toBeVisible();
  await expect(page.getByRole("link", { name: "rating: rating-1" })).toHaveAttribute("href", "/admin/valoraciones?detail=rating-1");
});

test("admin sidebar follows navigation and browser history", async ({ page, context }) => {
  await login(context, true);
  await page.goto("/admin");
  const sidebar = page.getByRole("navigation", { name: "Administración" });
  await expect(sidebar.getByRole("link", { name: "Principal" })).toHaveAttribute("aria-current", "page");
  await expect(sidebar.getByLabel("2 pendientes")).toBeVisible();
  await sidebar.getByRole("link", { name: "Auditoría" }).click();
  await expect(page).toHaveURL(/\/admin\/auditoria$/);
  await expect(page.getByRole("heading", { name: "Auditoría" })).toBeVisible();
  await page.goBack();
  await expect(sidebar.getByRole("link", { name: "Principal" })).toHaveAttribute("aria-current", "page");
});

test("admin design tokens style the frame, page header and active navigation", async ({ page, context }) => {
  await login(context, true);
  await page.goto("/admin");
  const frame = page.locator(".admin-frame");
  const header = page.getByRole("heading", { name: "Principal" }).locator("..");
  const nav = page.getByRole("navigation", { name: "Administración" });
  const active = nav.getByRole("link", { name: "Principal" });
  await expect(frame).toHaveCSS("background-color", "rgb(244, 247, 247)");
  await expect(header).toHaveCSS("border-bottom-width", "1px");
  await expect(active).toHaveCSS("border-inline-start-color", "rgb(184, 72, 36)");
  await expect(active).toHaveCSS("outline-style", "none");
  await page.getByRole("link", { name: "Amira Admin" }).focus();
  await page.keyboard.press("Tab");
  await expect(active).toBeFocused();
  await expect(active).toHaveCSS("outline-style", "solid");
  await expect(nav.getByLabel("2 pendientes")).toHaveCSS("color", "rgb(184, 72, 36)");
});

test("mobile opens and dismisses the menu without page overflow", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(context, true);
  await page.goto("/admin/auditoria");
  await expect(page.getByRole("navigation", { name: "Administración" })).not.toBeVisible();
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await expect(page.getByRole("dialog", { name: "Menú de administración" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Menú de administración" })).not.toBeVisible();
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    pageWidth: document.documentElement.scrollWidth,
    tableViewport: document.querySelector(".admin-table-scroll")?.clientWidth ?? 0,
    tableWidth: document.querySelector(".admin-table-scroll")?.scrollWidth ?? 0,
  }));
  expect(layout.pageWidth).toBe(layout.viewport);
  expect(layout.tableWidth).toBeGreaterThan(layout.tableViewport);
});

test("finance pages show mandate-model VAT and read-only settings", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(context, true);
  await page.goto("/admin?period=today");
  await expect(page.getByRole("heading", { name: "IVA débito de Amira" }).locator("..")).toContainText("$1.277");
  await expect(page.getByRole("link", { name: /Documentos de conductores/ }).last())
    .toHaveAttribute("href", "/admin/documentos?status=in_review");
  await page.getByRole("link", { name: "Comisiones e IVA" }).click();
  await expect(page.getByText("Base de cálculo para el F29. Validar con el contador.")).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Transportista de prueba" })).toBeVisible();
  await page.getByRole("link", { name: "Configuración" }).click();
  await expect(page.getByRole("main")).toContainText("24 horas");
  expect(errors).toEqual([]);
});

test("people pages expose the customer directory and its filters", async ({ page, context }) => {
  await login(context, true);
  await page.goto("/admin/clientes");
  await expect(page.getByRole("heading", { name: "Clientes", exact: true })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Buscar" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Exportar CSV" })).toBeVisible();
  await expect(page.getByText("No hay resultados con estos filtros")).toBeVisible();
});

test("document rejection requires a reason and opens the next pending document", async ({ page, context }) => {
  await login(context, true);
  let sentReason: string | undefined;
  await page.route("**/api/admin/review/documents/doc-1/reject", async (route) => {
    sentReason = route.request().postDataJSON().reason;
    await route.fulfill({ status: 200, json: { status: "updated" } });
  });
  await page.goto("/admin/documentos?detail=doc-1");
  await page.getByRole("dialog", { name: "Conductor de prueba" }).getByRole("button", { name: "Rechazar" }).click();
  const confirmation = page.getByRole("dialog", { name: "Rechazar: Conductor de prueba" });
  await confirmation.getByRole("button", { name: "Confirmar" }).click();
  expect(sentReason).toBeUndefined();
  await confirmation.getByLabel("Motivo").fill("El certificado está incompleto.");
  await confirmation.getByRole("button", { name: "Confirmar" }).click();
  await expect(page.getByRole("dialog", { name: "Segundo conductor" })).toBeVisible();
  expect(sentReason).toBe("El certificado está incompleto.");
});

test("an unclaimed chat does not request the transcript until a reason is entered", async ({ page, context }) => {
  await login(context, true);
  let reason: string | undefined;
  await page.route("**/api/admin/operations/chats/chat-1/transcript", async (route) => {
    reason = route.request().postDataJSON().reason;
    await route.fulfill({ json: { items: [{ id: "message", sender: "Cliente", text: "Mensaje privado", created_at: "2026-11-23T10:00:00Z" }], before: null } });
  });
  await page.goto("/admin/chats?detail=chat-1");
  await expect(page.getByText("Mensaje privado")).toHaveCount(0);
  await page.getByRole("button", { name: "Abrir conversación" }).click();
  expect(reason).toBeUndefined();
  await page.getByLabel("Motivo de acceso").fill("Investigar la solicitud de soporte.");
  await page.getByRole("button", { name: "Abrir conversación" }).click();
  await expect(page.getByText("Mensaje privado")).toBeVisible();
  expect(reason).toBe("Investigar la solicitud de soporte.");
});

test("payout release requires confirmation and shows the simulator summary", async ({ page, context }) => {
  await login(context, true);
  let releases = 0;
  await page.route("**/api/admin/transactions/payouts/release", async (route) => {
    releases += 1;
    await route.fulfill({ json: { due: 2, released: 1, missing_account: 1, missing_payment: 0, skipped: 0, failed: 0 } });
  });
  await page.goto("/admin/desembolsos");
  await page.getByRole("button", { name: "Liberar desembolsos vencidos" }).click();
  expect(releases).toBe(0);
  await page.getByRole("dialog").getByRole("button", { name: "Confirmar" }).click();
  await expect(page.getByText(/Liberados: 1/)).toBeVisible();
  expect(releases).toBe(1);
  await page.getByRole("link", { name: "Pagados" }).click();
  await expect(page).toHaveURL(/tab=paid/);
  await expect(page.getByRole("button", { name: "Liberar desembolsos vencidos" })).toHaveCount(0);
});

test("catalog offers creation for service types but not for fixed roles", async ({ page, context }) => {
  await login(context, true);
  let name: string | undefined;
  await page.route("**/api/admin/catalog/service-types", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    name = route.request().postDataJSON().name;
    await route.fulfill({ status: 201, json: { id: "fixture" } });
  });
  await page.goto("/admin/catalogos");
  await page.getByRole("button", { name: "Crear tipo de servicio" }).click();
  await page.getByRole("dialog").getByLabel("Nombre").fill("Transporte especial");
  await page.getByRole("dialog").getByRole("button", { name: "Crear", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(name).toBe("Transporte especial");
  await page.getByRole("link", { name: "Roles", exact: true }).click();
  await expect(page.getByRole("cell", { name: "client", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear tipo de servicio" })).toHaveCount(0);
});
