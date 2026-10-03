import { expect, test } from "@playwright/test";

const servicesResponse = {
  items: [
    {
      profileId: "profile-test-1",
      providerName: "Prestador de prueba",
      category: "mudanza",
      description: "Traslados de hogar dentro de la ciudad.",
      location: "Santiago",
      logoUrl: null,
      services: [{ serviceTypeId: "service-type-1", name: "Mudanzas" }],
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

test("landing links lead to service search and shared-route search", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Servicios" })).toHaveAttribute("href", "/servicios");
  await expect(page.getByRole("link", { name: "Explorar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(page.getByRole("link", { name: "Buscar viajes compartidos" })).toHaveAttribute("href", "/rutas-compartidas");
});

test("service search sends only supported filters and displays API results without invented trust claims", async ({ page }) => {
  let requestedUrl = "";
  await page.route("**/api/services?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({ json: servicesResponse });
  });

  await page.goto("/servicios");
  await expect(page.getByRole("heading", { name: "Prestador de prueba" })).toBeVisible();
  const card = page.locator(".service-result-card");
  await expect(card.getByRole("link", { name: "Ver perfil" })).toHaveAttribute("href", "/prestadores/profile-test-1");
  await expect(card.getByRole("button", { name: "Cotizar" })).toBeVisible();
  await expect(card.getByRole("link")).toHaveCount(1);
  await expect(card.getByRole("button")).toHaveCount(1);
  await expect(page.getByLabel("Categoría")).toHaveJSProperty("tagName", "SELECT");
  await expect.poll(() => page.getByLabel("Categoría").locator("option").evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value))).toEqual([
    "",
    "mudanza",
    "mercaderia",
    "flete",
    "escombros",
    "grua",
  ]);
  await page.getByLabel("Buscar por servicio o prestador").fill("camioneta");
  await page.getByLabel("Categoría").selectOption("mudanza");
  await page.getByLabel("Comuna o ciudad").fill("Santiago");
  await page.getByRole("button", { name: "Buscar servicios" }).click();

  await expect.poll(() => requestedUrl).toContain("q=camioneta");
  const query = new URL(requestedUrl).searchParams;
  expect(query.get("category")).toBe("mudanza");
  expect(query.get("location")).toBe("Santiago");
  expect(query.has("origin")).toBe(false);
  expect(query.has("destination")).toBe(false);
  await expect(page.getByText("No se muestran calificaciones ni verificaciones que Amira no ofrece.")).toBeVisible();
  await card.getByRole("button", { name: "Cotizar" }).click();
  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await expect(dialog.getByLabel("Servicio")).toHaveValue("service-type-1");
  await expect(dialog.getByLabel("Servicio")).toBeDisabled();
  await expect(page.getByRole("button", { name: /reservar|contratar/i })).toHaveCount(0);
});

test("provider quote dialog only offers matching services and allows choosing between them", async ({ page }) => {
  await page.route("**/api/services?*", async (route) => route.fulfill({
    json: {
      ...servicesResponse,
      items: [{
        ...servicesResponse.items[0],
        services: [
          { serviceTypeId: "service-type-1", name: "Mudanzas" },
          { serviceTypeId: "service-type-2", name: "Fletes" },
        ],
      }],
    },
  }));

  await page.goto("/servicios");
  const card = page.locator(".service-result-card");
  await card.getByRole("button", { name: "Cotizar" }).click();

  const serviceSelect = page.getByRole("dialog").getByLabel("Servicio");
  await expect(serviceSelect).toBeEnabled();
  await expect(serviceSelect.locator("option")).toHaveCount(2);
  await expect(serviceSelect.locator("option").nth(0)).toHaveAttribute("value", "service-type-1");
  await expect(serviceSelect.locator("option").nth(1)).toHaveAttribute("value", "service-type-2");
  await serviceSelect.selectOption("service-type-2");
  await expect(serviceSelect).toHaveValue("service-type-2");
});

test("service search exposes loading, empty, and error states", async ({ page }) => {
  await page.route("**/api/services?*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 650));
    await route.fulfill({ json: { ...servicesResponse, items: [], total: 0 } });
  });

  await page.goto("/servicios");
  await expect(page.getByRole("status")).toContainText("Cargando servicios");
  await expect(page.getByRole("status")).toContainText("No encontramos servicios");

  await page.route("**/api/services?*", (route) => route.abort());
  await page.getByLabel("Buscar por servicio o prestador").fill("error");
  await page.getByRole("button", { name: "Buscar servicios" }).click();
  await expect(page.locator(".marketplace-error")).toContainText("No pudimos cargar los servicios");
  await expect(page.getByRole("button", { name: "Reintentar" })).toBeVisible();
});

test("shared-route search sends supported filters and shows ordered stops without a booking action", async ({ page }) => {
  let requestedUrl = "";
  await page.route("**/api/shared-routes?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({
      json: {
        items: [{
          tripId: "trip-test-1",
          profileId: "profile-test-1",
          providerName: "Transportista de prueba",
          origin: "Santiago",
          destination: "Concepción",
          departureAt: "2026-10-12T09:00:00-03:00",
          stops: [
            { stopNumber: 1, estimatedAt: "2026-10-12T11:00:00-03:00" },
            { stopNumber: 2, estimatedAt: "2026-10-12T13:30:00-03:00" },
          ],
        }],
        total: 1,
        limit: 20,
        offset: 0,
      },
    });
  });

  await page.goto("/rutas-compartidas");
  await page.getByLabel("Origen").fill("Santiago");
  await page.getByLabel("Destino").fill("Concepción");
  await page.getByLabel("Desde la fecha").fill("2026-10-10");
  await page.getByLabel("Hasta la fecha").fill("2026-10-20");
  await page.getByRole("button", { name: "Buscar rutas" }).click();

  const query = new URL(requestedUrl).searchParams;
  expect(query.get("departureFrom")).toContain("2026-10-10T00:00:00");
  expect(query.get("departureFrom")).toMatch(/[+-]\d{2}:\d{2}$/);
  expect(query.get("origin")).toBe("Santiago");
  expect(query.get("destination")).toBe("Concepción");
  expect(query.get("departureTo")).toContain("2026-10-20T23:59:59.999");
  expect(query.get("departureTo")).toMatch(/[+-]\d{2}:\d{2}$/);
  await expect(page.getByRole("heading", { name: "Santiago a Concepción" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Transportista de prueba" })).toHaveAttribute("href", "/prestadores/profile-test-1");
  await expect(page.getByText("Parada intermedia 1")).toBeVisible();
  await expect(page.getByText("Parada intermedia 2")).toBeVisible();
  await expect(page.getByRole("button", { name: /reservar|contratar|consultar espacio/i })).toHaveCount(0);
  await expect(page.getByText(/No es una reserva/)).toBeVisible();
});

test("public provider profile shows real names and services, while quote requests require a verified customer session", async ({ page }) => {
  await page.route("**/api/providers/profile-test-1", async (route) => route.fulfill({
    json: {
      profileId: "profile-test-1",
      providerName: "Transportes del Sur",
      kind: "company",
      description: "Traslados y carga en la zona central.",
      location: "Santiago",
      ownerName: "Ana Pérez",
      drivers: [{ firstName: "Pedro", lastName: "Soto" }],
      services: [{ serviceTypeId: "service-type-1", name: "Mudanzas" }],
      vehicles: [{ brand: "Volvo", model: "FH", year: 2022, maximumWeight: "18000.00" }],
    },
  }));
  await page.goto("/prestadores/profile-test-1");
  await expect(page.getByRole("heading", { name: "Transportes del Sur" }).first()).toBeVisible();
  await expect(page.getByText("Ana Pérez")).toBeVisible();
  await expect(page.getByText("Pedro Soto")).toBeVisible();
  await expect(page.getByText("Volvo FH")).toBeVisible();
  await page.getByRole("button", { name: "Solicitar cotización" }).click();
  await expect(page.getByRole("dialog", { name: "Cuéntanos qué necesitas" })).toBeVisible();
  await page.getByLabel("Origen").fill("Santiago");
  await page.getByLabel("Destino").fill("Valparaíso");
  await page.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Inicia sesión con un correo confirmado");
  await expect(page.getByRole("dialog").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fprestadores%2Fprofile-test-1");
});

test("shared-route search renders loading, empty, and failure feedback", async ({ page }) => {
  await page.route("**/api/shared-routes?*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } });
  });
  await page.goto("/rutas-compartidas");
  await expect(page.getByRole("status")).toContainText("Cargando rutas");
  await expect(page.getByRole("status")).toContainText("No encontramos rutas");

  await page.route("**/api/shared-routes?*", (route) => route.abort());
  await page.getByLabel("Origen").fill("Santiago");
  await page.getByRole("button", { name: "Buscar rutas" }).click();
  await expect(page.locator(".marketplace-error")).toContainText("No pudimos cargar las rutas");
});

test("marketplace pages remain usable on a narrow mobile viewport", async ({ page }) => {
  await page.route("**/api/services?*", async (route) => route.fulfill({ json: { ...servicesResponse, items: [], total: 0 } }));
  await page.route("**/api/shared-routes?*", async (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/servicios");
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
  await expect(page.getByRole("button", { name: "Buscar servicios" })).toBeVisible();
  await page.goto("/rutas-compartidas");
  const routeDimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(routeDimensions.body).toBeLessThanOrEqual(routeDimensions.viewport);
  await expect(page.getByRole("button", { name: "Buscar rutas" })).toBeVisible();
});

test("mobile landing navigation exposes and opens the service and shared-route pages", async ({ page }) => {
  await page.route("**/api/services?*", async (route) => route.fulfill({ json: { ...servicesResponse, items: [], total: 0 } }));
  await page.goto("/");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  const navigation = page.getByRole("navigation", { name: "Navegación móvil" });
  await expect(navigation.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(navigation.getByRole("link", { name: "Rutas compartidas" })).toHaveAttribute("href", "/rutas-compartidas");
  await navigation.getByRole("link", { name: "Servicios" }).click();
  await expect(page).toHaveURL(/\/servicios$/);
  await expect(page.getByRole("heading", { name: "Encuentra el servicio que necesitas." })).toBeVisible();
});
