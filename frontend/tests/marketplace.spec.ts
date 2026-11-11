import { expect, test, type Page } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
});

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
  await expect(page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
  await expect(page.getByRole("link", { name: "Ver transportistas publicados" })).toHaveAttribute("href", "/servicios");
  await expect(page.getByRole("link", { name: "Ver viajes compartidos" })).toHaveAttribute("href", "/rutas-compartidas");
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
    "mudanzas",
    "carga-compartida",
    "mercaderia",
    "fletes",
    "escombros",
    "grua",
  ]);
  await page.getByLabel("Buscar por servicio o prestador").fill("camioneta");
  await page.getByLabel("Categoría").selectOption("mudanzas");
  await page.getByLabel("Región").selectOption("13");
  await page.getByLabel("Comuna").selectOption("13101");
  await page.getByRole("button", { name: "Buscar servicios" }).click();

  await expect.poll(() => requestedUrl).toContain("q=camioneta");
  const query = new URL(requestedUrl).searchParams;
  expect(query.get("serviceType")).toBe("mudanzas");
  expect(query.get("regionCode")).toBe("13");
  expect(query.get("communeCode")).toBe("13101");
  expect(query.has("category")).toBe(false);
  expect(query.has("location")).toBe(false);
  expect(query.has("origin")).toBe(false);
  expect(query.has("destination")).toBe(false);
  await expect(page.getByText("No se muestran calificaciones ni verificaciones que Amira no ofrece.")).toBeVisible();
  await card.getByRole("button", { name: "Cotizar" }).click();
  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await expect(dialog.getByLabel("Servicio")).toHaveValue("service-type-1");
  await expect(dialog.getByLabel("Servicio")).toBeDisabled();
  await expect(page.getByRole("button", { name: /reservar|contratar/i })).toHaveCount(0);
});

test("catalog category names keep their accents while the API filter uses the slug", async ({ page }) => {
  let requestedServiceType: string | null = null;
  await page.route("**/api/services?*", async (route) => {
    requestedServiceType = new URL(route.request().url()).searchParams.get("serviceType");
    await route.fulfill({ json: servicesResponse });
  });

  await page.goto("/servicios");
  const category = page.getByLabel("Categoría");
  for (const [label, expectedSlug] of [
    ["Transporte de mercadería", "mercaderia"],
    ["Servicios de grúa", "grua"],
  ]) {
    await category.selectOption({ label });
    await page.getByRole("button", { name: "Buscar servicios" }).click();
    await expect.poll(() => requestedServiceType).toBe(expectedSlug);
  }
});

test("service search reads its filters from the URL and the commune stays disabled until a region is chosen", async ({ page }) => {
  let requestedUrl = "";
  await page.route("**/api/services?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({ json: servicesResponse });
  });

  await page.goto("/servicios?serviceType=fletes&regionCode=05&communeCode=05101");
  await expect(page.getByLabel("Categoría")).toHaveValue("fletes");
  await expect(page.getByLabel("Región")).toHaveValue("05");
  await expect(page.getByLabel("Comuna")).toHaveValue("05101");
  await expect.poll(() => requestedUrl).toContain("communeCode=05101");
  const query = new URL(requestedUrl).searchParams;
  expect(query.get("serviceType")).toBe("fletes");
  expect(query.get("regionCode")).toBe("05");

  await page.getByLabel("Región").selectOption("");
  await expect(page.getByLabel("Comuna")).toBeDisabled();
  await expect(page.getByLabel("Comuna")).toHaveValue("");
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
  await expect(page.getByRole("status").filter({ hasText: "No encontramos servicios" })).toBeVisible();

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
          originCommuneCode: "13101",
          destinationCommuneCode: "08101",
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
  await page.getByLabel("Región de origen").selectOption("13");
  await page.getByLabel("Comuna de origen").selectOption("13101");
  await page.getByLabel("Región de destino").selectOption("08");
  await page.getByLabel("Comuna de destino").selectOption("08101");
  await page.getByLabel("Desde la fecha").fill("2026-10-10");
  await page.getByLabel("Hasta la fecha").fill("2026-10-20");
  await page.getByRole("button", { name: "Buscar rutas" }).click();

  const query = new URL(requestedUrl).searchParams;
  expect(query.get("departureFrom")).toContain("2026-10-10T00:00:00");
  expect(query.get("departureFrom")).toMatch(/[+-]\d{2}:\d{2}$/);
  expect(query.get("originCommuneCode")).toBe("13101");
  expect(query.get("destinationCommuneCode")).toBe("08101");
  expect(query.has("origin")).toBe(false);
  expect(query.has("destination")).toBe(false);
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
  await expect(page.getByText("Pedro Soto")).toBeVisible();
  await expect(page.getByText("Volvo FH")).toBeVisible();
  const profileNavigation = page.locator(".provider-profile-nav");
  await expect(profileNavigation.getByRole("link", { name: "Vehículos" })).toHaveAttribute("href", "#flota");
  await expect(profileNavigation.getByRole("link", { name: "Conductores" })).toHaveAttribute("href", "#conductores");
  await expect(profileNavigation.getByRole("link", { name: "Servicios" })).toHaveAttribute("href", "#servicios");
  await expect(page.getByText("15+ años de experiencia")).toHaveCount(0);
  const profileQuoteButton = page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true });
  await expect(profileQuoteButton).toBeVisible();
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
  await page.getByLabel("Región de origen").selectOption("13");
  await page.getByLabel("Comuna de origen").selectOption("13101");
  await page.getByLabel("Región de destino").selectOption("05");
  await page.getByLabel("Comuna de destino").selectOption("05101");
  await page.getByLabel("Dirección de origen", { exact: true }).fill("Av. Matta 123");
  await page.getByLabel("Dirección de destino", { exact: true }).fill("Av. Brasil 1");
  await page.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Inicia sesión con un correo confirmado");
  await expect(page.getByRole("dialog").getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fprestadores%2Fprofile-test-1");
  await page.getByRole("button", { name: "Cerrar solicitud" }).click();
  await page.setViewportSize({ width: 320, height: 760 });
  await expect(page.getByRole("button", { name: "Cotizar", exact: true })).toBeVisible();
  await expect(page.locator(".provider-profile-hero h1")).toBeVisible();
  await expect(page.locator(".provider-profile-hero")).toContainText("Empresa");
  await expect(page.locator(".provider-profile-hero")).toContainText("Santiago");
  await expect(page.getByRole("link", { name: "Volver a servicios" })).toBeVisible();
});

test("quote request uses commune codes for origin and destination and rejects past requested dates", async ({ page }) => {
  await page.route("**/api/providers/profile-quote", async (route) => route.fulfill({ json: {
    profileId: "profile-quote",
    providerName: "Fletes Costa",
    kind: "independent_driver",
    description: null,
    location: "Valparaíso",
    ownerName: "Alex Rojas",
    drivers: [],
    services: [{ serviceTypeId: "service-type-2", name: "Fletes" }],
    vehicles: [],
  } }));
  await page.goto("/prestadores/profile-quote");
  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await expect(dialog.getByLabel("Comuna de origen")).toBeDisabled();
  await expect(dialog.getByLabel("Comuna de destino")).toBeDisabled();
  await expect(dialog.getByLabel("Dirección de origen", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Fecha deseada")).toHaveAttribute("min", /^\d{4}-\d{2}-\d{2}$/);

  await dialog.getByLabel("Servicio").selectOption("service-type-2");
  await dialog.getByLabel("Región de origen").selectOption("13");
  await expect(dialog.getByLabel("Comuna de origen")).toBeEnabled();
  await dialog.getByLabel("Comuna de origen").selectOption("13114");
  await dialog.getByLabel("Región de destino").selectOption("05");
  await dialog.getByLabel("Comuna de destino").selectOption("05101");
  await dialog.getByLabel("Dirección de origen", { exact: true }).fill("Av. Matta 123");
  await dialog.getByLabel("Fecha deseada").fill("2020-01-01");
  await dialog.getByLabel("Hora deseada").fill("10:00");
  const underflow = await dialog.getByLabel("Fecha deseada").evaluate((element) => (element as HTMLInputElement).validity.rangeUnderflow);
  expect(underflow).toBe(true);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByRole("heading", { name: "Cuéntanos qué necesitas" })).toBeVisible();
});

test("quote request makes origin and destination addresses required and drops the measures field", async ({ page }) => {
  await page.route("**/api/providers/profile-required", async (route) => route.fulfill({ json: {
    profileId: "profile-required",
    providerName: "Fletes Norte",
    kind: "independent_driver",
    description: null,
    location: "Valparaíso",
    ownerName: "Alex Rojas",
    drivers: [],
    services: [{ serviceTypeId: "service-type-3", name: "Fletes" }],
    vehicles: [],
  } }));
  await page.goto("/prestadores/profile-required");
  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await expect(dialog.getByLabel("Dirección de origen", { exact: true })).toHaveAttribute("required", "");
  await expect(dialog.getByLabel("Dirección de destino", { exact: true })).toHaveAttribute("required", "");
  await expect(dialog.getByLabel("Peso estimado (kg) (opcional)")).toBeVisible();
  await expect(dialog.getByLabel("Volumen estimado (m³) (opcional)")).toBeVisible();
  await expect(dialog.getByLabel("Medidas de la carga")).toHaveCount(0);
});

test("quote request requires date and time together and allows both empty", async ({ page }) => {
  await page.route("**/api/providers/profile-schedule", async (route) => route.fulfill({ json: {
    profileId: "profile-schedule",
    providerName: "Fletes Sur",
    kind: "independent_driver",
    description: null,
    location: "Valparaíso",
    ownerName: "Alex Rojas",
    drivers: [],
    services: [{ serviceTypeId: "service-type-4", name: "Fletes" }],
    vehicles: [],
  } }));
  await page.goto("/prestadores/profile-schedule");
  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await dialog.getByLabel("Servicio").selectOption("service-type-4");
  await dialog.getByLabel("Región de origen").selectOption("13");
  await dialog.getByLabel("Comuna de origen").selectOption("13114");
  await dialog.getByLabel("Región de destino").selectOption("05");
  await dialog.getByLabel("Comuna de destino").selectOption("05101");
  await dialog.getByLabel("Dirección de origen", { exact: true }).fill("Av. Matta 123");
  await dialog.getByLabel("Dirección de destino", { exact: true }).fill("Av. Brasil 1");

  await dialog.getByLabel("Fecha deseada").fill("2099-01-15");
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(dialog.locator("#quote-schedule-error")).toHaveText("Indica la fecha y la hora deseadas, o deja ambas vacías.");

  await dialog.getByLabel("Fecha deseada").fill("");
  await dialog.getByLabel("Hora deseada").fill("10:00");
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(dialog.locator("#quote-schedule-error")).toHaveText("Indica la fecha y la hora deseadas, o deja ambas vacías.");

  await dialog.getByLabel("Hora deseada").fill("");
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(dialog.locator("#quote-schedule-error")).toHaveCount(0);
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
  await expect(page.getByText("No hay servicios publicados")).toBeVisible();
  const profileQuoteButton = page.getByRole("button", { name: "Cotizar", exact: true });
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
  await expect(page.getByText("27 valoraciones")).toBeVisible();
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
  await expect(page.getByRole("status").filter({ hasText: "No encontramos rutas" })).toBeVisible();

  await page.route("**/api/shared-routes?*", (route) => route.abort());
  await page.getByLabel("Región de origen").selectOption("13");
  await page.getByLabel("Comuna de origen").selectOption("13101");
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

// Request photos: the customer attaches images in the quote modal and they upload after the request exists.
const photoJpeg = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(64)]);
const photoPng = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64)]);
const imageProfileResponse = {
  profileId: "profile-images",
  providerName: "Fletes Centro",
  kind: "independent_driver",
  description: null,
  location: "Valparaíso",
  ownerName: "Alex Rojas",
  drivers: [],
  services: [{ serviceTypeId: "service-type-5", name: "Fletes" }],
  vehicles: [],
};

async function openImageQuoteDialog(page: Page) {
  await page.route("**/api/providers/profile-images", async (route) => route.fulfill({ json: imageProfileResponse }));
  await page.goto("/prestadores/profile-images");
  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();
  return page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
}

async function fillRequiredQuote(dialog: ReturnType<Page["getByRole"]>) {
  await dialog.getByLabel("Servicio").selectOption("service-type-5");
  await dialog.getByLabel("Región de origen").selectOption("13");
  await dialog.getByLabel("Comuna de origen").selectOption("13114");
  await dialog.getByLabel("Región de destino").selectOption("05");
  await dialog.getByLabel("Comuna de destino").selectOption("05101");
  await dialog.getByLabel("Dirección de origen", { exact: true }).fill("Av. Matta 123");
  await dialog.getByLabel("Dirección de destino", { exact: true }).fill("Av. Brasil 1");
}

const photoCustomer = {
  id: "user-photo-1",
  aud: "authenticated",
  role: "authenticated",
  email: "persona@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};
const photoSmsFactor = { id: "factor-sms-photo", factor_type: "phone", status: "verified", phone: "+56912345678" };

function photoSession(aal: "aal1" | "aal2", tokenId: string) {
  const payload = Buffer.from(JSON.stringify({ aal, exp: 2000000000, sub: photoCustomer.id })).toString("base64url");
  return {
    access_token: `eyJhbGciOiJub25lIn0.${payload}.${tokenId}`,
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: "refresh-test-token",
    user: photoCustomer,
  };
}

async function signInAsPhotoCustomer(page: Page) {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/auth/v1", "");
    const method = request.method();
    if (path === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: photoSession("aal1", "password-aal1-photo") });
      return;
    }
    if (path === "/user" && method === "GET") {
      await route.fulfill({ json: { ...photoCustomer, factors: [photoSmsFactor] } });
      return;
    }
    if (path === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: [photoSmsFactor], phone: [photoSmsFactor], totp: [] } });
      return;
    }
    if (path === "/factors/factor-sms-photo/challenge" && method === "POST") {
      await route.fulfill({ json: { id: "challenge-photo", expires_at: Date.now() + 300000 } });
      return;
    }
    if (path === "/factors/factor-sms-photo/verify" && method === "POST") {
      await route.fulfill({ json: photoSession("aal2", "verified-aal2-photo") });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${path}` } });
  });
  await page.route("**/api/account/me", async (route) => route.fulfill({ json: { user_id: "account-photo-1", role: "client", profile_id: null } }));
  await page.goto("/login?next=%2Fprestadores%2Fprofile-images");
  await page.locator("#auth-email").fill(photoCustomer.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/prestadores\/profile-images$/);
}

test("quote modal attaches photos with a preview and lets the customer remove one", async ({ page }) => {
  const dialog = await openImageQuoteDialog(page);

  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([
    { name: "mueble.jpg", mimeType: "image/jpeg", buffer: photoJpeg },
    { name: "caja.png", mimeType: "image/png", buffer: photoPng },
  ]);
  await expect(dialog.getByRole("img", { name: "Vista previa de la foto 1" })).toBeVisible();
  await expect(dialog.getByRole("img", { name: "Vista previa de la foto 2" })).toBeVisible();

  await dialog.getByRole("button", { name: "Quitar la foto 1" }).click();
  await expect(dialog.getByRole("img", { name: "Vista previa de la foto 1" })).toHaveCount(1);
  await expect(dialog.getByRole("img", { name: "Vista previa de la foto 2" })).toHaveCount(0);
});

test("quote modal refuses non-image and oversize photos in Spanish and caps the count at five", async ({ page }) => {
  const dialog = await openImageQuoteDialog(page);

  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([
    { name: "notas.jpg", mimeType: "text/plain", buffer: Buffer.from("no es una imagen") },
  ]);
  await expect(dialog.getByRole("alert").filter({ hasText: "Solo puedes adjuntar fotos en formato JPEG, PNG o WebP." })).toBeVisible();

  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([
    { name: "grande.jpg", mimeType: "image/jpeg", buffer: Buffer.concat([photoJpeg, Buffer.alloc(5 * 1024 * 1024)]) },
  ]);
  await expect(dialog.getByRole("alert").filter({ hasText: "La foto no puede superar los 5 MB." })).toBeVisible();

  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles(
    Array.from({ length: 6 }, (_, index) => ({ name: `foto-${index}.jpg`, mimeType: "image/jpeg", buffer: photoJpeg })),
  );
  await expect(dialog.getByRole("alert").filter({ hasText: "Puedes adjuntar hasta 5 fotos por solicitud." })).toBeVisible();
  // The first five are kept; only the sixth is refused.
  await expect(dialog.getByRole("img", { name: /Vista previa de la foto/ })).toHaveCount(5);
});

test("after the request is created each photo is uploaded to that request", async ({ page }) => {
  const uploads: string[] = [];
  let created = 0;
  await page.route("**/api/service-requests", async (route) => {
    created += 1;
    await route.fulfill({ status: 201, json: { requestId: "request-img-1", status: "pending" } });
  });
  await page.route("**/api/requests/request-img-1/images", async (route) => {
    uploads.push(route.request().method());
    await route.fulfill({ status: 201, json: { imageId: `image-${uploads.length}` } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await fillRequiredQuote(dialog);
  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([
    { name: "mueble.jpg", mimeType: "image/jpeg", buffer: photoJpeg },
    { name: "caja.png", mimeType: "image/png", buffer: photoPng },
  ]);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("heading", { name: "Solicitud enviada" })).toBeVisible();
  expect(created).toBe(1);
  expect(uploads).toEqual(["POST", "POST"]);
});

test("quote modal sends acceptsSharing false when the customer leaves the sharing choice as it comes", async ({ page }) => {
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/service-requests", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: { requestId: "request-share-default", status: "pending" } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await expect(dialog.getByLabel("¿Aceptas compartir el vehículo con otro cliente?")).toHaveValue("false");
  await fillRequiredQuote(dialog);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("heading", { name: "Solicitud enviada" })).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ acceptsSharing: false });
});

test("quote modal sends acceptsSharing true when the customer chooses Sí", async ({ page }) => {
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/service-requests", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: { requestId: "request-share-yes", status: "pending" } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await dialog.getByLabel("¿Aceptas compartir el vehículo con otro cliente?").selectOption("true");
  await fillRequiredQuote(dialog);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("heading", { name: "Solicitud enviada" })).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ acceptsSharing: true });
});

test("a normal quote request without a shared trip sends no requestedTripId", async ({ page }) => {
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/service-requests", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: { requestId: "request-plain", status: "pending" } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await fillRequiredQuote(dialog);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("heading", { name: "Solicitud enviada" })).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).not.toHaveProperty("requestedTripId");
});

test("a failed photo upload keeps the request sent and says some photos were not attached", async ({ page }) => {
  let created = 0;
  await page.route("**/api/service-requests", async (route) => {
    created += 1;
    await route.fulfill({ status: 201, json: { requestId: "request-img-2", status: "pending" } });
  });
  await page.route("**/api/requests/request-img-2/images", async (route) => {
    await route.fulfill({ status: 502, json: { detail: "The request photo could not be stored. Try again." } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await fillRequiredQuote(dialog);
  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([
    { name: "mueble.jpg", mimeType: "image/jpeg", buffer: photoJpeg },
  ]);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("heading", { name: "Solicitud enviada" })).toBeVisible();
  await expect(dialog.getByRole("alert")).toHaveText("La solicitud se envió, pero no pudimos adjuntar algunas fotos.");
  expect(created).toBe(1);
});

test("the close button cannot dismiss the dialog while photos are uploading, and the notice still appears", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/service-requests", async (route) => route.fulfill({ status: 201, json: { requestId: "request-close-1", status: "pending" } }));
  await page.route("**/api/requests/request-close-1/images", async (route) => {
    await gate;
    await route.fulfill({ status: 502, json: { detail: "The request photo could not be stored. Try again." } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await fillRequiredQuote(dialog);
  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([{ name: "mueble.jpg", mimeType: "image/jpeg", buffer: photoJpeg }]);
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  const close = dialog.getByRole("button", { name: "Cerrar solicitud" });
  await expect(close).toBeDisabled();
  await expect(dialog).toBeVisible();

  release();
  await expect(dialog.getByRole("alert")).toHaveText("La solicitud se envió, pero no pudimos adjuntar algunas fotos.");
  await expect(dialog).toBeVisible();
  await expect(close).toBeEnabled();
});

test("the Escape key cannot dismiss the dialog while photos are uploading, and the notice still appears", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/service-requests", async (route) => route.fulfill({ status: 201, json: { requestId: "request-escape-1", status: "pending" } }));
  await page.route("**/api/requests/request-escape-1/images", async (route) => {
    await gate;
    await route.fulfill({ status: 502, json: { detail: "The request photo could not be stored. Try again." } });
  });
  await signInAsPhotoCustomer(page);
  const dialog = await openImageQuoteDialog(page);
  await fillRequiredQuote(dialog);
  await dialog.getByLabel("Fotos de la carga (opcional)").setInputFiles([{ name: "mueble.jpg", mimeType: "image/jpeg", buffer: photoJpeg }]);
  const imageUpload = page.waitForRequest("**/api/requests/request-escape-1/images");
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();
  await imageUpload;

  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();

  release();
  await expect(dialog.getByRole("alert")).toHaveText("La solicitud se envió, pero no pudimos adjuntar algunas fotos.");
  await expect(dialog).toBeVisible();
});

test("when idle the dialog closes with the close button and with Escape", async ({ page }) => {
  const dialog = await openImageQuoteDialog(page);
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cerrar solicitud" }).click();
  await expect(dialog).toBeHidden();
});
