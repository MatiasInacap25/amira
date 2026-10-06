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
    "mercadería",
    "flete",
    "escombros",
    "grúa",
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

test("accented service category labels send accent-preserving API filters", async ({ page }) => {
  let requestedCategory: string | null = null;
  await page.route("**/api/services?*", async (route) => {
    requestedCategory = new URL(route.request().url()).searchParams.get("category");
    await route.fulfill({ json: servicesResponse });
  });

  await page.goto("/servicios");
  const category = page.getByLabel("Categoría");
  for (const [label, expectedCategory] of [
    ["Transporte de mercadería", "mercadería"],
    ["Servicios de grúa", "grúa"],
  ]) {
    await category.selectOption({ label });
    await page.getByRole("button", { name: "Buscar servicios" }).click();
    await expect.poll(() => requestedCategory).toBe(expectedCategory);
  }
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
      services: [
        { serviceTypeId: "service-type-1", name: "Mudanzas" },
        { serviceTypeId: "service-type-2", name: "Fletes" },
      ],
      vehicles: [{ brand: "Volvo", model: "FH", year: 2022, maximumWeight: "18000.00" }],
    },
  }));
  await page.goto("/prestadores/profile-test-1");
  await expect(page.locator(".provider-profile-hero h1")).toHaveText("Transportes del Sur");
  await expect(page.getByText("Ana Pérez")).toBeVisible();
  await expect(page.getByText("Pedro Soto")).toBeVisible();
  await expect(page.getByText("Volvo FH")).toBeVisible();
  const profileNavigation = page.locator(".provider-profile-nav");
  await expect(profileNavigation.getByRole("link", { name: "Resumen" })).toHaveAttribute("href", "#resumen");
  await expect(profileNavigation.getByRole("link", { name: "Flota" })).toHaveAttribute("href", "#flota");
  await expect(profileNavigation.getByRole("link", { name: "Conductores" })).toHaveAttribute("href", "#conductores");
  await expect(profileNavigation.getByRole("link", { name: "Servicios" })).toHaveAttribute("href", "#servicios");
  const metrics = page.locator(".provider-profile-metrics > div");
  await expect(metrics.nth(0).locator("strong")).toHaveText("1");
  await expect(metrics.nth(0).locator("span")).toHaveText("vehículo");
  await expect(metrics.nth(1).locator("strong")).toHaveText("1");
  await expect(metrics.nth(1).locator("span")).toHaveText("conductor");
  await expect(page.getByText("15+ años de experiencia")).toHaveCount(0);
  const profileQuoteButton = page.getByRole("button", { name: "Solicitar cotización", exact: true });
  await expect(profileQuoteButton).toHaveCount(1);
  await expect(page.locator(".provider-profile-hero").getByRole("button", { name: "Solicitar cotización", exact: true })).toBeVisible();
  await profileQuoteButton.click();
  await expect(page.getByRole("dialog", { name: "Cuéntanos qué necesitas" })).toBeVisible();
  const serviceSelect = page.getByRole("dialog").getByLabel("Servicio");
  const submitQuote = page.getByRole("button", { name: "Enviar solicitud" });
  await expect(serviceSelect).toBeEnabled();
  await expect(serviceSelect).toHaveValue("");
  await expect(serviceSelect.locator("option").first()).toContainText("Elige un servicio");
  await expect(submitQuote).toBeDisabled();
  await serviceSelect.selectOption("service-type-2");
  await expect(submitQuote).toBeEnabled();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await profileQuoteButton.click();
  await expect(serviceSelect).toHaveValue("");
  await expect(submitQuote).toBeDisabled();
  await serviceSelect.selectOption("service-type-2");
  await page.getByLabel("Origen").fill("Santiago");
  await page.getByLabel("Destino").fill("Valparaíso");
  await page.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Inicia sesión con un correo confirmado");
  await expect(page.getByRole("dialog").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fprestadores%2Fprofile-test-1");
  await page.getByRole("button", { name: "Cerrar solicitud" }).click();
  await page.setViewportSize({ width: 320, height: 760 });
  await expect(page.getByRole("button", { name: "Solicitar cotización", exact: true })).toHaveCount(1);
  await expect(page.locator(".provider-profile-hero").getByRole("button", { name: "Solicitar cotización", exact: true })).toBeVisible();
  await expect(page.locator(".provider-profile-hero h1")).toBeVisible();
  await expect(page.locator(".provider-profile-identity-details")).toContainText("Empresa");
  await expect(page.locator(".provider-profile-identity-details")).toContainText("Santiago");
  await expect(page.getByRole("link", { name: "Volver a servicios" })).toBeVisible();
});

test("provider profile skip target remains available while loading, failed, and retrying", async ({ page }) => {
  let attempts = 0;
  let allowSuccessfulRetry = false;
  await page.route("**/api/providers/profile-retry", async (route) => {
    attempts += 1;
    if (!allowSuccessfulRetry) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      await route.abort();
      return;
    }
    await route.fulfill({ json: {
      profileId: "profile-retry",
      providerName: "Prestador recuperado",
      kind: "company",
      description: null,
      location: "Valparaíso",
      ownerName: "Alex Rojas",
      drivers: [],
      services: [],
      vehicles: [],
    } });
  });
  await page.goto("/prestadores/profile-retry");
  const target = page.locator("#provider-profile-content");
  await expect(page.getByRole("status")).toContainText("Cargando perfil");
  await expect(target).toHaveCount(1);
  await expect(target).toHaveAttribute("tabindex", "-1");
  const skipLink = page.getByRole("link", { name: "Ir al perfil" });
  await skipLink.focus();
  await skipLink.press("Enter");
  await expect(target).toBeFocused();
  await expect(page.locator(".marketplace-error")).toContainText("No pudimos cargar este perfil");
  await expect(page.locator("#provider-profile-content")).toHaveCount(1);
  allowSuccessfulRetry = true;
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.locator(".provider-profile-hero h1")).toHaveText("Prestador recuperado");
  await expect(page.locator("#provider-profile-content")).toHaveCount(1);
  expect(attempts).toBeGreaterThanOrEqual(2);
});

test("public provider profile keeps truthful empty states and fits a 320px viewport", async ({ page }) => {
  await page.route("**/api/providers/profile-empty", async (route) => route.fulfill({
    json: {
      profileId: "profile-empty",
      providerName: "Prestador sin inventario",
      kind: "independent_driver",
      description: null,
      location: null,
      ownerName: "Alex Rojas",
      drivers: [],
      services: [],
      vehicles: [],
    },
  }));
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/prestadores/profile-empty");

  await expect(page.locator(".provider-profile-mobile-nav")).toBeVisible();
  await expect(page.getByText("Este prestador no ha informado vehículos.")).toBeVisible();
  await expect(page.getByText("Este prestador no ha informado conductores vinculados.")).toBeVisible();
  await expect(page.getByText("No hay servicios publicados")).toBeVisible();
  const profileQuoteButton = page.locator(".provider-profile-hero").getByRole("button", { name: "Solicitar cotización", exact: true });
  await expect(profileQuoteButton).toBeDisabled();
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});

test("public provider profile displays real ratings and keeps the review section usable on mobile", async ({ page }) => {
  await page.route("**/api/providers/profile-rated", async (route) => route.fulfill({ json: {
    profileId: "profile-rated",
    providerName: "Transportes con valoraciones",
    kind: "company",
    description: null,
    location: "Santiago",
    ownerName: "Alex Rojas",
    drivers: [],
    services: [],
    vehicles: [],
    ratings: {
      averageRating: 4.25,
      ratingCount: 27,
      recent: [
        { rating: 5, comment: "Coordinación clara y entrega puntual.", createdAt: "2026-10-04T00:00:00Z" },
        { rating: 4, comment: null, createdAt: "2026-10-02T00:00:00Z" },
      ],
    },
  } }));
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/prestadores/profile-rated");

  const mobileNavigation = page.locator(".provider-profile-mobile-nav");
  await expect(mobileNavigation.getByRole("link", { name: "Valoraciones" })).toHaveAttribute("href", "#valoraciones");
  await mobileNavigation.getByRole("link", { name: "Valoraciones" }).click();
  await expect(page.getByRole("heading", { name: "Valoraciones", level: 2 })).toBeVisible();
  await expect(page.getByText("4,25 de 5", { exact: true })).toBeVisible();
  await expect(page.getByText("27 valoraciones", { exact: true })).toBeVisible();
  await expect(page.getByText("Coordinación clara y entrega puntual.")).toBeVisible();
  await expect(page.getByText("4 de octubre de 2026")).toBeVisible();
  await expect(page.getByText("Sin comentario")).toBeVisible();
  await expect(page.getByText("Valoración de Cliente Demo")).toHaveCount(0);
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});

test("public provider profile distinguishes an authoritative empty rating summary", async ({ page }) => {
  await page.route("**/api/providers/profile-no-ratings", async (route) => route.fulfill({ json: {
    profileId: "profile-no-ratings",
    providerName: "Prestador sin valoraciones",
    kind: "company",
    description: null,
    location: null,
    ownerName: "Alex Rojas",
    drivers: [],
    services: [],
    vehicles: [],
    ratings: { averageRating: null, ratingCount: 0, recent: [] },
  } }));
  await page.goto("/prestadores/profile-no-ratings");

  await expect(page.getByRole("heading", { name: "Valoraciones", level: 2 })).toBeVisible();
  await expect(page.getByText("Este prestador aún no tiene valoraciones.")).toBeVisible();
  await expect(page.getByText("0 de 5", { exact: true })).toHaveCount(0);
});

test("public provider profile does not claim there are no ratings when an older API omits them", async ({ page }) => {
  await page.route("**/api/providers/profile-old-api", async (route) => route.fulfill({ json: {
    profileId: "profile-old-api",
    providerName: "Prestador API anterior",
    kind: "company",
    description: null,
    location: null,
    ownerName: "Alex Rojas",
    drivers: [],
    services: [],
    vehicles: [],
  } }));
  await page.goto("/prestadores/profile-old-api");

  await expect(page.getByRole("heading", { name: "Valoraciones", level: 2 })).toBeVisible();
  await expect(page.getByText("Las valoraciones no están disponibles en este momento.")).toBeVisible();
  await expect(page.getByText("Este prestador aún no tiene valoraciones.")).toHaveCount(0);
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
