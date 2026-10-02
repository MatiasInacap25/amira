import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("presents both customer and transport-provider paths in Spanish", async ({ page }) => {
  await expect(page).toHaveTitle(/Amira \| Transporte/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByRole("heading", { name: "El servicio que necesitas, con el camión adecuado." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ofrecer mis servicios" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tu camión y tu trabajo, bajo tus propias condiciones." })).toBeVisible();
});

test("desktop navigation targets the matching business sections", async ({ page }) => {
  const navigation = page.getByRole("navigation", { name: "Navegación principal" });
  await expect(navigation.getByRole("link", { name: "Empresas" })).toHaveAttribute("href", "#empresas");
  await expect(navigation.getByRole("link", { name: "Para transportistas" })).toHaveAttribute("href", "#transportistas");
});

test("validates a local service search and presents an honest demo result", async ({ page }) => {
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.locator(".form-alert")).toContainText("Selecciona un servicio");
  await expect(page.getByLabel("Tipo de servicio")).toHaveAttribute("aria-describedby", "search-error-title");
  await expect(page.locator(".form-alert a")).toHaveAttribute("href", "#service-type");

  await page.getByLabel("Tipo de servicio").selectOption("mudanza");
  await page.getByLabel("Origen").fill("Santiago");
  await page.getByLabel("Destino").fill("Providencia");
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.getByRole("status")).toContainText("demostración");
  await expect(page.getByText("Sin prestadores reales conectados todavía")).toBeVisible();
});

test("category cards select the matching service in the request form", async ({ page }) => {
  await page.getByRole("button", { name: /Recolección de escombros/ }).click();
  await expect(page.getByLabel("Tipo de servicio")).toHaveValue("escombros");
});

test("escombro requests need an origin but no destination", async ({ page }) => {
  await page.getByLabel("Tipo de servicio").selectOption("escombros");
  await expect(page.getByLabel("Destino")).toBeDisabled();
  await page.getByLabel("Origen").fill("Ñuñoa");
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.locator(".search-results")).toContainText("desde Ñuñoa");
});

test("FAQ disclosures can be opened using their native keyboard control", async ({ page }) => {
  const question = page.getByText("¿Cómo funciona el pago protegido en Amira?");
  await question.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/no está disponible en esta etapa/i)).toBeVisible();
});

test("mobile navigation opens and exposes the service and provider actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  const menu = page.getByRole("button", { name: "Cerrar menú" });
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Navegación móvil" }).getByRole("link", { name: "Buscar servicios" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navegación móvil" }).getByRole("link", { name: "Rutas compartidas" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navegación móvil" }).getByRole("link", { name: "Registrar mi vehículo" })).toHaveAttribute("href", "/registro?intent=provider");
});

test("the page fits a narrow phone viewport without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
