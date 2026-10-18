import { expect, test } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
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

test("validates the required service type before navigating to the service search", async ({ page }) => {
  await expect(page.getByLabel("Tipo de servicio").locator("option")).toHaveCount(7);
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.locator(".form-alert")).toContainText("Selecciona un servicio");
  await expect(page.getByLabel("Tipo de servicio")).toHaveAttribute("aria-describedby", "search-error-title");
  await expect(page.locator(".form-alert a")).toHaveAttribute("href", "#service-type");

  await page.getByLabel("Tipo de servicio").selectOption("mudanzas");
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page).toHaveURL(/\/servicios\?serviceType=mudanzas$/);
});

test("category cards select the matching service in the request form", async ({ page }) => {
  await page.getByRole("button", { name: /Recolección de escombros/ }).click();
  await expect(page.getByLabel("Tipo de servicio")).toHaveValue("escombros");
});

test("home search sends the service type and commune codes to the service search", async ({ page }) => {
  await page.getByLabel("Tipo de servicio").selectOption("escombros");
  await page.getByLabel("Región").selectOption("13");
  await page.getByLabel("Comuna").selectOption("13114");
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page).toHaveURL(/\/servicios\?serviceType=escombros&regionCode=13&communeCode=13114$/);
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

test("hero actions point to the search form and the provider registration", async ({ page }) => {
  const hero = page.getByRole("region", { name: "El servicio que necesitas, con el camión adecuado." });
  await expect(hero.getByRole("link", { name: /Buscar un servicio/ })).toHaveAttribute("href", "#buscar");
  await expect(hero.getByRole("link", { name: /Quiero transportar/ })).toHaveAttribute("href", "/registro?intent=provider");
});

test("header links route to the search, shared routes, login, and registration pages", async ({ page }) => {
  const navigation = page.getByRole("navigation", { name: "Navegación principal" });
  await expect(navigation.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(navigation.getByRole("link", { name: "Rutas compartidas" })).toHaveAttribute("href", "/rutas-compartidas");
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/registro");
  await expect(page.getByRole("link", { name: "Ofrecer mis servicios" }).first()).toHaveAttribute("href", "/registro?intent=provider");
});

test("service cards render one button per catalog service with its description", async ({ page }) => {
  const cards = page.locator(".service-grid button.service-card");
  await expect(cards).toHaveCount(6);
  await expect(page.getByRole("button", { name: /^Mudanzas: Hogares y oficinas/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Servicios de grúa: Traslado de vehículos/ })).toBeVisible();
});

test("submitting an empty search focuses the error summary and marks the select invalid", async ({ page }) => {
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.locator(".form-alert")).toBeFocused();
  await expect(page.getByLabel("Tipo de servicio")).toHaveAttribute("aria-invalid", "true");
  await expect(page).toHaveURL(/\/$/);
});

test("choosing a service card clears a pending service validation error", async ({ page }) => {
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page.locator(".form-alert")).toBeVisible();
  await page.getByRole("button", { name: /^Mudanzas:/ }).click();
  await expect(page.locator(".form-alert")).toHaveCount(0);
  await expect(page.getByLabel("Tipo de servicio")).toHaveValue("mudanzas");
});

test("search with only a service sends no location parameters", async ({ page }) => {
  await page.getByLabel("Tipo de servicio").selectOption("mudanzas");
  await page.getByRole("button", { name: "Buscar servicio" }).click();
  await expect(page).toHaveURL(/\/servicios\?serviceType=mudanzas$/);
});

test("mobile menu closes after choosing a section link", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("navigation", { name: "Navegación móvil" }).getByRole("link", { name: "Empresas" }).click();
  await expect(page.getByRole("navigation", { name: "Navegación móvil" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abrir menú" })).toHaveAttribute("aria-expanded", "false");
});

test("provider profile samples explain they are not active offers and can be dismissed", async ({ page }) => {
  await page.getByRole("button", { name: "Ver perfil y cotizar" }).first().click();
  const notice = page.getByRole("status");
  await expect(notice).toContainText("Los perfiles de transportistas son ejemplos ilustrativos");
  await notice.getByRole("button", { name: "Cerrar aviso" }).click();
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("carrier registration is explained as a demo and collects no data", async ({ page }) => {
  await expect(page.getByText("Registro de demostración. Todavía no recibimos solicitudes ni documentos.")).toBeVisible();
  await page.getByRole("button", { name: "Registrar mi vehículo" }).click();
  await expect(page.getByRole("status")).toContainText("No se recopilaron datos.");
});

test("the four how-it-works steps are listed in order", async ({ page }) => {
  const steps = page.locator(".steps-grid .step-card h3");
  await expect(steps).toHaveText([
    "Publica tu necesidad",
    "Coordina los detalles",
    "Acuerda las condiciones",
    "Recibe tu carga",
  ]);
  await expect(page.getByRole("link", { name: /Conoce más/ })).toHaveAttribute("href", "#faq");
});

test("trust section marks every protection feature as not yet active", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Confianza que se construye con hechos" })).toBeVisible();
  await expect(page.locator(".trust-grid .planned-label")).toHaveCount(4);
  await expect(page.locator(".trust-grid article", { hasText: "Pago en custodia" }).locator(".planned-label")).toHaveText("No disponible");
});

test("FAQ lists six questions, all collapsed by default", async ({ page }) => {
  const items = page.locator("details.faq-item");
  await expect(items).toHaveCount(6);
  for (const item of await items.all()) {
    await expect(item).not.toHaveAttribute("open", "");
  }
});

test("shared-route example is labelled unavailable and links to the shared routes page", async ({ page }) => {
  await expect(page.getByText("Ejemplo, no disponible")).toBeVisible();
  await expect(page.getByRole("link", { name: /Buscar viajes compartidos/ })).toHaveAttribute("href", "/rutas-compartidas");
});

test("footer privacy link shows the unpublished-terms notice", async ({ page }) => {
  await page.getByRole("link", { name: "Privacidad y términos" }).click();
  await expect(page.getByRole("status")).toContainText("Los términos, la política de privacidad y el canal de ayuda aún no están publicados.");
});

test("closing call to action sends visitors back to the search form", async ({ page }) => {
  const closing = page.getByRole("region", { name: "Mueve tu carga o haz crecer tu negocio de transporte." });
  await expect(closing.getByRole("link", { name: /Solicitar un servicio/ })).toHaveAttribute("href", "#buscar");
});

test("closing call to action offers the provider registration", async ({ page }) => {
  const closing = page.getByRole("region", { name: "Mueve tu carga o haz crecer tu negocio de transporte." });
  await expect(closing.getByRole("link", { name: /Ofrecer mis servicios/ })).toHaveAttribute("href", "/registro?intent=provider");
});

test("footer links point to the sections and pages they name", async ({ page }) => {
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByRole("link", { name: "Servicios", exact: true })).toHaveAttribute("href", "/servicios");
  await expect(footer.getByRole("link", { name: "Viajes compartidos" })).toHaveAttribute("href", "/rutas-compartidas");
  await expect(footer.getByRole("link", { name: "Cómo funciona" })).toHaveAttribute("href", "#como-funciona");
  await expect(footer.getByRole("link", { name: "Solicitar un servicio" })).toHaveAttribute("href", "#buscar");
  await expect(footer.getByRole("link", { name: "Ofrecer mis servicios" })).toHaveAttribute("href", "/registro?intent=provider");
  await expect(footer.getByRole("link", { name: "Centro de ayuda" })).toHaveAttribute("href", "#faq");
  await expect(footer.getByRole("link", { name: "Política de pagos" })).toHaveAttribute("href", "#pago");
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

test("skip link moves keyboard users to the main content", async ({ page }) => {
  const skipLink = page.getByRole("link", { name: "Ir al contenido" });
  await skipLink.focus();
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#contenido$/);
  await expect(page.getByRole("main")).toBeVisible();
});

test("choosing a service card moves focus to the service select", async ({ page }) => {
  await page.getByRole("button", { name: /^Mudanzas:/ }).click();
  await expect(page.getByLabel("Tipo de servicio")).toBeFocused();
});

test("value strip summarises the three differentiators", async ({ page }) => {
  const strip = page.getByRole("region", { name: "Lo que distingue a Amira" });
  await expect(strip.getByText("Personas y pymes")).toBeVisible();
  await expect(strip.getByText("Oferta independiente")).toBeVisible();
  await expect(strip.getByText("Desde tu comuna")).toBeVisible();
});

test("every provider sample is labelled as illustrative and shows the same notice", async ({ page }) => {
  await expect(page.getByText("EJEMPLO ILUSTRATIVO")).toHaveCount(3);
  const profileButtons = page.getByRole("button", { name: "Ver perfil y cotizar" });
  await expect(profileButtons).toHaveCount(3);
  await profileButtons.nth(2).click();
  await expect(page.getByRole("status")).toContainText("Los perfiles de transportistas son ejemplos ilustrativos");
});

test("carrier section lists the four benefits", async ({ page }) => {
  const benefits = page.locator(".benefit-list li strong");
  await expect(benefits).toHaveText([
    "Autonomía tarifaria",
    "Información clara",
    "Más tipos de clientes",
    "Facturación según tu servicio",
  ]);
});

test("mobile menu closes from its toggle and from the request link", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("button", { name: "Cerrar menú" }).click();
  await expect(page.getByRole("navigation", { name: "Navegación móvil" })).toHaveCount(0);

  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("navigation", { name: "Navegación móvil" }).getByRole("link", { name: "Solicitar un servicio" }).click();
  await expect(page.getByRole("navigation", { name: "Navegación móvil" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abrir menú" })).toHaveAttribute("aria-expanded", "false");
});

test("secondary links route to the service catalogue, carrier section, and help anchor", async ({ page }) => {
  await expect(page.getByRole("link", { name: "Explorar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(page.getByRole("link", { name: /Registra tu vehículo y encuentra nuevos clientes aquí/ })).toHaveAttribute("href", "#transportistas");
  await expect(page.getByRole("link", { name: /Más información/ })).toHaveAttribute("href", "#ayuda");
});

test("FAQ answer for shipping quotes opens when its summary is clicked", async ({ page }) => {
  const answer = page.getByText(/Cada prestador determina su precio/);
  await expect(answer).toBeHidden();
  await page.getByText("¿Cómo se calculan las cotizaciones de los fletes?").click();
  await expect(answer).toBeVisible();
});
