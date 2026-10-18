import { expect, test, type Page } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

const baseProfile = {
  profileId: "profile-prestador",
  providerName: "Transportes Andes",
  kind: "company",
  description: "Traslados y carga en la zona central.",
  location: "Santiago",
  communeCode: "13101",
  communeName: "Santiago",
  regionName: "Metropolitana de Santiago",
  ownerName: "Ana Pérez",
  drivers: [{ firstName: "Pedro", lastName: "Soto", isOwner: true }],
  services: [
    { serviceTypeId: "service-type-1", name: "Mudanzas" },
    { serviceTypeId: "service-type-2", name: "Fletes" },
  ],
  vehicles: [{ brand: "Volvo", model: "FH", year: 2022, maximumWeight: "18000.00" }],
  ratings: null,
};

async function mockProfile(page: Page, profileId: string, overrides: Record<string, unknown> = {}) {
  await page.route(`**/api/providers/${profileId}`, (route) => route.fulfill({ json: { ...baseProfile, profileId, ...overrides } }));
}

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
});

test("each published service has its own quote button that preselects that service", async ({ page }) => {
  await mockProfile(page, "profile-services");
  await page.goto("/prestadores/profile-services");

  const servicesSection = page.locator("#servicios");
  await expect(servicesSection.getByRole("heading", { name: "Servicios", level: 2 })).toBeVisible();
  await expect(servicesSection.locator(".provider-service-item")).toHaveCount(2);

  await page.getByRole("button", { name: "Cotizar Fletes" }).click();
  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Servicio")).toHaveValue("service-type-2");
  await dialog.getByRole("button", { name: "Cancelar" }).click();
  await expect(dialog).toBeHidden();
});

test("quote bar uses singular and plural wording for the published service count", async ({ page }) => {
  await mockProfile(page, "profile-two-services");
  await page.goto("/prestadores/profile-two-services");
  const quoteBar = page.locator(".provider-quote-bar");
  await expect(quoteBar.locator("strong")).toHaveText("Transportes Andes");
  await expect(quoteBar.locator("span")).toHaveText("2 servicios publicados");

  await mockProfile(page, "profile-one-service", { services: [{ serviceTypeId: "service-type-1", name: "Mudanzas" }] });
  await page.goto("/prestadores/profile-one-service");
  await expect(page.locator(".provider-quote-bar span")).toHaveText("1 servicio publicado");
});

test("profile without services disables every quote entry point and explains why", async ({ page }) => {
  await mockProfile(page, "profile-no-services", { services: [] });
  await page.goto("/prestadores/profile-no-services");

  await expect(page.getByText("Este prestador no tiene servicios publicados para cotizar.")).toBeVisible();
  await expect(page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true })).toBeDisabled();
  await expect(page.locator(".provider-quote-bar span")).toHaveText("0 servicios publicados");

  // The hero button is hidden below the mobile breakpoint; the sticky bar takes over as the quote entry point.
  await page.setViewportSize({ width: 320, height: 760 });
  await expect(page.locator(".provider-quote-bar").getByRole("button", { name: "Cotizar", exact: true })).toBeDisabled();
});

test("vehicle cards show the weight limit or a fallback when details are missing", async ({ page }) => {
  await mockProfile(page, "profile-vehicles", {
    vehicles: [
      { brand: "Volvo", model: "FH", year: 2022, maximumWeight: "18000.00" },
      { brand: "Scania", model: "R", year: null, maximumWeight: null },
    ],
  });
  await page.goto("/prestadores/profile-vehicles");

  const vehicles = page.locator("#flota .provider-vehicle-item");
  await expect(vehicles).toHaveCount(2);
  await expect(vehicles.nth(0).locator("strong")).toHaveText("Volvo FH");
  await expect(vehicles.nth(0).locator("small")).toHaveText("2022 · Carga máxima 18000.00 kg");
  await expect(vehicles.nth(1).locator("strong")).toHaveText("Scania R");
  await expect(vehicles.nth(1).locator("small")).toHaveText("Sin más datos informados");
});

test("company profile marks the owner driver and lists drivers in the section navigation", async ({ page }) => {
  await mockProfile(page, "profile-company", {
    drivers: [
      { firstName: "Pedro", lastName: "Soto", isOwner: true },
      { firstName: "Luis", lastName: "Vega", isOwner: false },
    ],
  });
  await page.goto("/prestadores/profile-company");

  await expect(page.locator(".provider-kind-badge")).toHaveText("Empresa");
  await expect(page.locator(".provider-profile-sidebar").getByRole("link", { name: "Conductores" })).toHaveAttribute("href", "#conductores");
  const drivers = page.locator("#conductores .provider-driver-grid li");
  await expect(drivers).toHaveCount(2);
  await expect(drivers.nth(0).getByText("Titular")).toBeVisible();
  await expect(drivers.nth(1).getByText("Titular")).toHaveCount(0);
});

test("independent driver profile has no drivers section or drivers navigation link", async ({ page }) => {
  await mockProfile(page, "profile-independent", { kind: "independent_driver", drivers: [] });
  await page.goto("/prestadores/profile-independent");

  await expect(page.locator(".provider-kind-badge")).toHaveText("Conductor independiente");
  await expect(page.locator(".provider-profile-sidebar").getByRole("link", { name: "Conductores" })).toHaveCount(0);
  await expect(page.locator("#conductores")).toHaveCount(0);
});

test("single rating shows singular review count and a summary without recent comments", async ({ page }) => {
  await mockProfile(page, "profile-single-rating", {
    ratings: { averageRating: 5, ratingCount: 1, recent: [] },
  });
  await page.goto("/prestadores/profile-single-rating");

  await expect(page.locator(".provider-profile-rating-line")).toContainText("1 valoración");
  const ratings = page.locator("#valoraciones");
  await expect(ratings.locator(".provider-rating-summary strong")).toHaveText("5,00 de 5");
  await expect(ratings.getByText("No hay comentarios recientes.")).toBeVisible();
});

test("profile without ratings says so in the hero and in the ratings section", async ({ page }) => {
  await mockProfile(page, "profile-no-rating-data", { ratings: null });
  await page.goto("/prestadores/profile-no-rating-data");

  await expect(page.locator(".provider-profile-rating-empty")).toHaveText("Aún no hay valoraciones");
  await expect(page.locator("#valoraciones").getByText("Aún no hay valoraciones")).toBeVisible();
});

// FIXME(app): RatingLine (provider-profile-view.tsx) returns "Aún no hay valoraciones" whenever averageRating is null,
// even though ratingCount is 3; the ratings section below the hero says "Promedio no disponible" for the same data.
test.fixme("ratings without a computed average show a fallback label instead of a number", async ({ page }) => {
  await mockProfile(page, "profile-no-average", {
    ratings: { averageRating: null, ratingCount: 3, recent: [] },
  });
  await page.goto("/prestadores/profile-no-average");

  await expect(page.locator(".provider-profile-rating-line")).toContainText("3 valoraciones");
  await expect(page.locator(".provider-profile-rating-line")).not.toContainText(" de 5");
  await expect(page.locator("#valoraciones").getByText("Promedio no disponible")).toBeVisible();
});

test("unknown provider shows the error state with retry and renders no profile content", async ({ page }) => {
  await page.route("**/api/providers/profile-missing", (route) => route.fulfill({ status: 404, json: { detail: "Not found" } }));
  await page.goto("/prestadores/profile-missing");

  const errorState = page.locator(".marketplace-error");
  await expect(errorState.getByRole("heading", { name: "No pudimos cargar este perfil" })).toBeVisible();
  await expect(errorState.getByText("El perfil puede no estar publicado")).toBeVisible();
  await expect(errorState.getByRole("button", { name: "Reintentar" })).toBeVisible();
  await expect(page.locator(".provider-profile-hero")).toHaveCount(0);
  await expect(page.locator(".provider-quote-bar")).toHaveCount(0);
});

// FIXME(app): for an id with a space and slash, the page sends "/api/providers/perfil%2520con%252F1" to the API instead of "/api/providers/perfil%20con%2F1" (observed; cause not isolated).
test.fixme("profile id with reserved characters is sent to the API encoded as one path segment", async ({ page }) => {
  let requestedPath = "";
  await page.route(/\/api\/providers\//, async (route) => {
    requestedPath = new URL(route.request().url()).pathname;
    await route.fulfill({ json: { ...baseProfile, profileId: "perfil con/1", providerName: "Perfil codificado" } });
  });
  await page.goto(`/prestadores/${encodeURIComponent("perfil con/1")}`);

  await expect(page.locator(".provider-profile-hero h1")).toHaveText("Perfil codificado");
  expect(requestedPath).toBe("/api/providers/perfil%20con%2F1");
});

test("back link returns to the services catalog and section links jump to their sections", async ({ page }) => {
  await mockProfile(page, "profile-navigation");
  await page.goto("/prestadores/profile-navigation");

  const sidebar = page.locator(".provider-profile-sidebar");
  await expect(sidebar.getByRole("link", { name: "Volver a servicios" })).toHaveAttribute("href", "/servicios");

  await sidebar.getByRole("link", { name: "Vehículos" }).click();
  await expect(page).toHaveURL(/#flota$/);
  await expect(page.getByRole("heading", { name: "Vehículos", level: 2 })).toBeVisible();
});

test("signed-out visitor is asked to sign in before a quote request is sent", async ({ page }) => {
  await mockProfile(page, "profile-signed-out");
  await page.goto("/prestadores/profile-signed-out");

  await page.locator(".provider-profile-hero").getByRole("button", { name: "Cotizar", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Cuéntanos qué necesitas" });
  await dialog.getByLabel("Servicio").selectOption("service-type-1");
  await dialog.getByLabel("Región de origen").selectOption("13");
  await dialog.getByLabel("Comuna de origen").selectOption("13101");
  await dialog.getByLabel("Región de destino").selectOption("05");
  await dialog.getByLabel("Comuna de destino").selectOption("05101");
  await dialog.getByRole("button", { name: "Enviar solicitud" }).click();

  await expect(dialog.getByRole("alert")).toContainText("Inicia sesión con un correo confirmado");
  await expect(dialog.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Fprestadores%2Fprofile-signed-out");
});

test("long provider name and unbroken vehicle model fit a 320px viewport", async ({ page }) => {
  await mockProfile(page, "profile-long-name", {
    providerName: "Transportesupercalifragilisticoexpialidociosoyotrolargonombresinespacios",
    vehicles: [{ brand: "Mercedes", model: "Actrosaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", year: 2021, maximumWeight: "24000.00" }],
  });
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/prestadores/profile-long-name");

  await expect(page.locator(".provider-profile-hero h1")).toBeVisible();
  await expect(page.locator(".provider-quote-bar")).toBeVisible();
  const dimensions = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
