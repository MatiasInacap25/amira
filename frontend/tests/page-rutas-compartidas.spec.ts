import { expect, test, type Page } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
});

function sharedRoute(overrides: Record<string, unknown> = {}) {
  return {
    tripId: "trip-test-1",
    profileId: "profile-test-1",
    providerName: "Transportista de prueba",
    origin: "Santiago",
    destination: "Concepción",
    originCommuneCode: "13101",
    destinationCommuneCode: "08101",
    departureAt: "2026-10-12T09:00:00-03:00",
    stops: null,
    ...overrides,
  };
}

function routesPage(items: ReturnType<typeof sharedRoute>[], total: number, offset = 0) {
  return { items, total, limit: 20, offset };
}

async function mockSharedRoutes(page: Page, respond: (query: URLSearchParams) => unknown) {
  const requests: URLSearchParams[] = [];
  await page.route("**/api/shared-routes?*", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    requests.push(query);
    await route.fulfill({ json: respond(query) });
  });
  return requests;
}

test("page shows its heading, skip link, back link and booking disclaimer", async ({ page }) => {
  await mockSharedRoutes(page, () => routesPage([], 0));

  await page.goto("/rutas-compartidas");

  await expect(page.getByRole("heading", { name: "Encuentra una ruta publicada.", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rutas compartidas", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ir a los resultados" })).toHaveAttribute("href", "#resultados");
  await expect(page.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/");
  await expect(page.getByText("Consultar una ruta no reserva espacio ni inicia una solicitud. Amira no procesa pagos ni confirma reservas.")).toBeVisible();
});

test("initial load requests the first page without commune or date filters", async ({ page }) => {
  const requests = await mockSharedRoutes(page, () => routesPage([], 0));

  await page.goto("/rutas-compartidas");

  await expect.poll(() => requests.length).toBeGreaterThan(0);
  for (const query of requests) {
    expect(query.get("offset")).toBe("0");
    expect(query.get("limit")).toBe("20");
    expect(query.has("originCommuneCode")).toBe(false);
    expect(query.has("destinationCommuneCode")).toBe(false);
    expect(query.has("departureFrom")).toBe(false);
    expect(query.has("departureTo")).toBe(false);
  }
});

test("optional origin and destination are omitted from the request when left empty", async ({ page }) => {
  const requests = await mockSharedRoutes(page, () => routesPage([], 0));

  await page.goto("/rutas-compartidas");
  await expect(page.getByLabel("Comuna de origen")).toBeDisabled();
  await expect(page.getByLabel("Comuna de destino")).toBeDisabled();
  await page.getByLabel("Desde la fecha").fill("2026-10-01");
  await page.getByRole("button", { name: "Buscar rutas" }).click();

  await expect.poll(() => requests.at(-1)?.get("departureFrom")).toMatch(/^2026-10-01T00:00:00/);
  const query = requests.at(-1);
  expect(query?.has("originCommuneCode")).toBe(false);
  expect(query?.has("destinationCommuneCode")).toBe(false);
});

test("date range that ends before it starts blocks the search until the dates are corrected", async ({ page }) => {
  const requests = await mockSharedRoutes(page, () => routesPage([], 0));

  await page.goto("/rutas-compartidas");
  await expect(page.getByRole("heading", { name: "No encontramos rutas con esos filtros" })).toBeVisible();
  const requestsBeforeSearch = requests.length;

  await page.getByLabel("Desde la fecha").fill("2026-10-20");
  await page.getByLabel("Hasta la fecha").fill("2026-10-10");
  await page.getByRole("button", { name: "Buscar rutas" }).click();

  const alert = page.locator("#route-date-error");
  await expect(alert).toHaveText("La fecha de término debe ser igual o posterior a la fecha de inicio.");
  await expect(page.getByLabel("Desde la fecha")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Hasta la fecha")).toHaveAttribute("aria-describedby", "route-date-error");
  expect(requests).toHaveLength(requestsBeforeSearch);

  await page.getByLabel("Hasta la fecha").fill("2026-10-25");
  await expect(alert).toHaveCount(0);
  await expect(page.getByLabel("Desde la fecha")).not.toHaveAttribute("aria-invalid", "true");

  await page.getByRole("button", { name: "Buscar rutas" }).click();
  await expect.poll(() => requests.length).toBeGreaterThan(requestsBeforeSearch);
  const query = requests.at(-1);
  expect(query?.get("departureFrom")).toMatch(/^2026-10-20T00:00:00/);
  expect(query?.get("departureTo")).toMatch(/^2026-10-25T23:59:59\.999/);
});

test("result count uses the singular and plural forms", async ({ page }) => {
  let items = [sharedRoute()];
  await mockSharedRoutes(page, () => routesPage(items, items.length));

  await page.goto("/rutas-compartidas");
  await expect(page.locator(".results-count")).toHaveText("1 ruta");

  items = [sharedRoute(), sharedRoute({ tripId: "trip-test-2", providerName: "Otro transportista" })];
  await page.getByLabel("Desde la fecha").fill("2026-10-01");
  await page.getByRole("button", { name: "Buscar rutas" }).click();
  await expect(page.locator(".results-count")).toHaveText("2 rutas");
  await expect(page.locator(".shared-route-card")).toHaveCount(2);
});

test("route cards fall back to a pending departure and omit the stops block when none were reported", async ({ page }) => {
  await mockSharedRoutes(page, () => routesPage([
    sharedRoute({ tripId: "trip-no-date", providerName: "Sin fecha", departureAt: null, stops: null }),
    sharedRoute({ tripId: "trip-bad-date", providerName: "Fecha inválida", departureAt: "no-es-fecha", stops: [] }),
  ], 2));

  await page.goto("/rutas-compartidas");

  const cards = page.locator(".shared-route-card");
  await expect(cards).toHaveCount(2);
  await expect(cards.getByText("Salida: Fecha por confirmar")).toHaveCount(2);
  await expect(page.getByRole("heading", { name: "Paradas informadas" })).toHaveCount(0);
  await expect(cards.first().getByText(/No es una reserva/)).toBeVisible();
});

test("provider link encodes the profile identifier in the profile URL", async ({ page }) => {
  await mockSharedRoutes(page, () => routesPage([
    sharedRoute({ profileId: "profile/with space", providerName: "Transporte con código" }),
  ], 1));

  await page.goto("/rutas-compartidas");

  await expect(page.getByRole("link", { name: "Transporte con código" })).toHaveAttribute("href", "/prestadores/profile%2Fwith%20space");
});

test("pagination moves between pages, disables the edges and returns to the first page on a new search", async ({ page }) => {
  const requests = await mockSharedRoutes(page, (query) => {
    const offset = Number(query.get("offset"));
    const count = offset === 40 ? 5 : 20;
    const items = Array.from({ length: count }, (_, index) => sharedRoute({ tripId: `trip-${offset + index}` }));
    return routesPage(items, 45, offset);
  });

  await page.goto("/rutas-compartidas");
  const pagination = page.getByRole("navigation", { name: "Páginas de rutas" });
  await expect(pagination.getByRole("button", { name: "Anterior" })).toBeDisabled();
  await expect(pagination).toContainText("Resultados 1–20 de 45");
  await expect(pagination.getByRole("button", { name: "Siguiente" })).toBeEnabled();

  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination).toContainText("Resultados 21–40 de 45");
  await expect(pagination.getByRole("button", { name: "Anterior" })).toBeEnabled();
  expect(requests.at(-1)?.get("offset")).toBe("20");

  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination).toContainText("Resultados 41–45 de 45");
  await expect(pagination.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  await expect(page.locator(".shared-route-card")).toHaveCount(5);

  await pagination.getByRole("button", { name: "Anterior" }).click();
  await expect(pagination).toContainText("Resultados 21–40 de 45");

  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination).toContainText("Resultados 41–45 de 45");
  await page.getByLabel("Desde la fecha").fill("2026-10-01");
  await page.getByRole("button", { name: "Buscar rutas" }).click();
  await expect(pagination).toContainText("Resultados 1–20 de 45");
  expect(requests.at(-1)?.get("offset")).toBe("0");
});

test("pagination is hidden when all results fit on one page", async ({ page }) => {
  await mockSharedRoutes(page, () => routesPage([sharedRoute()], 1));

  await page.goto("/rutas-compartidas");

  await expect(page.locator(".shared-route-card")).toHaveCount(1);
  await expect(page.getByRole("navigation", { name: "Páginas de rutas" })).toHaveCount(0);
});

test("a failed search shows the error state and retrying loads the results", async ({ page }) => {
  let failing = false;
  await mockSharedRoutes(page, () => routesPage([sharedRoute()], 1));
  await page.route("**/api/shared-routes?*", async (route) => {
    if (failing) {
      await route.abort();
      return;
    }
    await route.fallback();
  });

  await page.goto("/rutas-compartidas");
  await expect(page.locator(".shared-route-card")).toHaveCount(1);

  failing = true;
  await page.getByLabel("Desde la fecha").fill("2026-10-01");
  await page.getByRole("button", { name: "Buscar rutas" }).click();
  const error = page.locator(".marketplace-error");
  await expect(error).toContainText("No pudimos cargar las rutas");
  await expect(error).toContainText("No mostraremos rutas de ejemplo como si estuvieran disponibles.");
  await expect(page.locator(".shared-route-card")).toHaveCount(0);
  await expect(page.getByText("0 rutas")).toHaveCount(0);

  failing = false;
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(error).toHaveCount(0);
  await expect(page.locator(".shared-route-card")).toHaveCount(1);
  await expect(page.locator(".results-count")).toHaveText("1 ruta");
});

test("results with stops stay within a 320px viewport", async ({ page }) => {
  await mockSharedRoutes(page, () => routesPage([
    sharedRoute({
      stops: [
        { stopNumber: 1, estimatedAt: "2026-10-12T11:00:00-03:00" },
        { stopNumber: 2, estimatedAt: "2026-10-12T13:30:00-03:00" },
      ],
    }),
  ], 1));
  await page.setViewportSize({ width: 320, height: 760 });

  await page.goto("/rutas-compartidas");

  await expect(page.getByRole("heading", { name: "Santiago a Concepción" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Paradas informadas" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Buscar rutas" })).toBeVisible();
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
