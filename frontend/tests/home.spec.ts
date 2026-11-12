import { expect, test } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
  await page.goto("/");
});

test("names the category and the country in the hero, in Spanish", async ({ page }) => {
  await expect(page).toHaveTitle(/Amira \| Transporte/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const hero = page.getByRole("region", { name: "Transporte de carga en todo Chile" });
  await expect(hero.getByRole("heading", { level: 1 })).toHaveText("Transporte de carga en todo Chile");
  await expect(hero.getByRole("link", { name: /Buscar un servicio/ })).toHaveAttribute("href", "#buscar");
});

test("desktop navigation links to the service pages and the landing sections", async ({ page }) => {
  const navigation = page.getByRole("navigation", { name: "Navegación principal" });
  await expect(navigation.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(navigation.getByRole("link", { name: "Rutas compartidas" })).toHaveAttribute("href", "/rutas-compartidas");
  await expect(navigation.getByRole("link", { name: "Cómo funciona" })).toHaveAttribute("href", "#como-funciona");
  await expect(navigation.getByRole("link", { name: "Transportistas" })).toHaveAttribute("href", "#transportistas");
  await expect(page.getByRole("banner").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  await expect(page.getByRole("banner").getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");
  await expect(page.getByRole("banner").getByRole("link", { name: "Buscar un servicio" })).toHaveAttribute("href", "#buscar");
});

test("lists one button per catalog service with its description", async ({ page }) => {
  const services = page.getByRole("list", { name: "Tipos de servicio" }).getByRole("button");
  await expect(services).toHaveCount(6);
  await expect(page.getByRole("button", { name: /^Mudanzas: Hogares y oficinas/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Servicios de grúa: Traslado de vehículos/ })).toBeVisible();
});

test("choosing a service selects it in the form and moves focus to the select", async ({ page }) => {
  await page.getByRole("button", { name: /Recolección de escombros/ }).click();
  await expect(page.getByLabel("Tipo de servicio")).toHaveValue("escombros");
  await expect(page.getByLabel("Tipo de servicio")).toBeFocused();
  await expect(page.getByRole("button", { name: /Recolección de escombros/ })).toHaveAttribute("aria-pressed", "true");
});

test("an empty search shows a focused error tied to the service select and stays on the page", async ({ page }) => {
  await expect(page.getByLabel("Tipo de servicio").locator("option")).toHaveCount(7);
  await page.getByRole("button", { name: "Buscar servicio", exact: true }).click();
  const alert = page.locator(".lp-form__alert");
  await expect(alert).toContainText("Elige un tipo de servicio para buscar.");
  await expect(alert).toBeFocused();
  await expect(alert.getByRole("link")).toHaveAttribute("href", "#service-type");
  await expect(page.getByLabel("Tipo de servicio")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Tipo de servicio")).toHaveAttribute("aria-describedby", "search-error");
  await expect(page).toHaveURL(/\/$/);
});

test("choosing a service clears a pending validation error", async ({ page }) => {
  await page.getByRole("button", { name: "Buscar servicio", exact: true }).click();
  await expect(page.locator(".lp-form__alert")).toBeVisible();
  await page.getByRole("button", { name: /^Mudanzas:/ }).click();
  await expect(page.locator(".lp-form__alert")).toHaveCount(0);
});

test("a search with only a service sends no location parameters", async ({ page }) => {
  await page.getByLabel("Tipo de servicio").selectOption("mudanzas");
  await page.getByRole("button", { name: "Buscar servicio", exact: true }).click();
  await expect(page).toHaveURL(/\/servicios\?serviceType=mudanzas$/);
});

test("a search sends the service type and the commune codes", async ({ page }) => {
  await page.getByLabel("Tipo de servicio").selectOption("escombros");
  await page.locator("#home-search-location-region").selectOption("13");
  await page.locator("#home-search-location-commune").selectOption("13114");
  await page.getByRole("button", { name: "Buscar servicio", exact: true }).click();
  await expect(page).toHaveURL(/\/servicios\?serviceType=escombros&regionCode=13&communeCode=13114$/);
});

test("the search form links carriers to their section", async ({ page }) => {
  await expect(page.getByRole("link", { name: "Registra tu vehículo" })).toHaveAttribute("href", "#transportistas");
});

test("the carrier section lists four benefits and links to provider registration", async ({ page }) => {
  const carriers = page.getByRole("region", { name: /Para transportistas con camión o camioneta/ });
  await expect(carriers.locator(".lp-benefits strong")).toHaveText([
    "Tú pones el precio",
    "Cada solicitud con sus datos",
    "Particulares y empresas",
    "Boleta o factura, según tu servicio",
  ]);
  await expect(carriers.getByRole("link", { name: /Registrar mi vehículo/ })).toHaveAttribute("href", "/registro?intent=provider");
  await expect(page.locator("#empresas")).toHaveCount(1);
});

test("the shared-trip section links to the shared routes page and shows the catalog coverage", async ({ page }) => {
  const shared = page.getByRole("region", { name: "Viajes compartidos con espacio libre" });
  await expect(shared.getByRole("link", { name: /Ver viajes compartidos/ })).toHaveAttribute("href", "/rutas-compartidas");
  await expect(shared.locator('[data-moment="counter-rolls"] .t-stat')).toHaveCount(2);
  await expect(shared.getByText("regiones con búsqueda por comuna")).toBeVisible();
  await expect(shared.getByText("comunas para origen y destino")).toBeVisible();
});

test("every FAQ answer is open on load, including the payments answer", async ({ page }) => {
  const items = page.locator(".lp-faq__item");
  await expect(items).toHaveCount(6);
  await expect(page.locator("details.faq-item")).toHaveCount(0);
  await expect(page.locator("#pago")).toContainText("Amira no procesa ni retiene pagos");
  await expect(page.getByText(/Cada transportista fija su precio/)).toBeVisible();
});

test("the closing call to action and the footer point where they say", async ({ page }) => {
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByRole("heading", { name: "Encuentra transportista en tu comuna" })).toBeVisible();
  await expect(footer.getByRole("link", { name: /Buscar un servicio/ })).toHaveAttribute("href", "#buscar");
  await expect(footer.getByRole("link", { name: "Servicios", exact: true })).toHaveAttribute("href", "/servicios");
  await expect(footer.getByRole("link", { name: "Rutas compartidas" })).toHaveAttribute("href", "/rutas-compartidas");
  await expect(footer.getByRole("link", { name: "Ofrecer mis servicios" })).toHaveAttribute("href", "/registro?intent=provider");
  await expect(footer.getByRole("link", { name: "Pagos" })).toHaveAttribute("href", "#pago");
  await expect(footer.getByRole("link", { name: "Fotografías vía Wikimedia Commons" })).toHaveAttribute("href", "/creditos");
});

test("the credits page names the author and licence of every landing photograph", async ({ page }) => {
  await page.goto("/creditos");
  await expect(page.getByRole("heading", { level: 1, name: "Créditos de fotografías" })).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(3);
  await expect(page.getByRole("listitem").filter({ hasText: "CC BY-SA 2.0" })).toContainText("order_242 from Chile");
});

test("the hero collage can be paused", async ({ page }) => {
  const pause = page.getByRole("button", { name: "Pausar la animación" });
  await pause.click();
  await expect(page.getByRole("button", { name: "Reanudar la animación" })).toHaveAttribute("aria-pressed", "true");
});

test("mobile navigation opens, lists the account and provider links, and closes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await expect(page.getByRole("button", { name: "Cerrar menú" })).toHaveAttribute("aria-expanded", "true");
  const sheet = page.getByRole("navigation", { name: "Navegación móvil" });
  await expect(sheet.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(sheet.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");
  await expect(sheet.getByRole("link", { name: "Registrar mi vehículo" })).toHaveAttribute("href", "/registro?intent=provider");
  await sheet.getByRole("link", { name: "Empresas" }).click();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abrir menú" })).toHaveAttribute("aria-expanded", "false");
});

test("the mobile menu closes with Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("navigation", { name: "Navegación móvil" })).toHaveCount(0);
});

test("the page fits a narrow phone viewport without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});

test("every in-page anchor points to an element that exists on the page", async ({ page }) => {
  const targets = await page.locator('a[href^="#"]').evaluateAll((links) =>
    links.map((link) => link.getAttribute("href")!.slice(1)),
  );
  expect(targets.length).toBeGreaterThan(0);
  for (const id of new Set(targets)) {
    await expect(page.locator(`[id="${id}"]`), `anchor #${id}`).toHaveCount(1);
  }
});

test("the skip link is the first tab stop and moves to the main content", async ({ page }) => {
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Ir al contenido" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#contenido$/);
});

test("a signed-out visitor on the landing page makes no chat request", async ({ page }) => {
  const chatRequests: string[] = [];
  await page.route("**/api/chats/**", async (route) => {
    chatRequests.push(route.request().url());
    await route.fulfill({ status: 401, json: { detail: "Unauthorized" } });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  expect(chatRequests).toEqual([]);
});
