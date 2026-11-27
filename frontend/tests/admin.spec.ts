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
