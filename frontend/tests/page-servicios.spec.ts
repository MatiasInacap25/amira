import { expect, test } from "@playwright/test";
import { mockCatalogs } from "./support/catalog-fixtures";

test.beforeEach(async ({ page }) => {
  await mockCatalogs(page);
});

function serviceItem(index: number, overrides: Record<string, unknown> = {}) {
  return {
    profileId: `profile-page-${index}`,
    providerName: `Prestador de página ${index}`,
    category: "mudanza",
    description: `Descripción del prestador ${index}.`,
    location: "Santiago",
    logoUrl: null,
    services: [{ serviceTypeId: "service-type-1", name: "Mudanzas" }],
    ...overrides,
  };
}

test("skip link points to the results section on the services page", async ({ page }) => {
  await page.route("**/api/services?*", (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.goto("/servicios");

  const skipLink = page.getByRole("link", { name: "Ir a los resultados" });
  await expect(skipLink).toHaveAttribute("href", "#resultados");
  await expect(page.locator("#resultados")).toHaveCount(1);
});

test("results counter uses the singular and plural forms", async ({ page }) => {
  let total = 1;
  await page.route("**/api/services?*", (route) => route.fulfill({
    json: { items: [serviceItem(1)], total, limit: 20, offset: 0 },
  }));

  await page.goto("/servicios");
  await expect(page.getByText("1 resultado", { exact: true })).toBeVisible();

  total = 2;
  await page.getByLabel("Buscar por servicio o prestador").fill("dos");
  await page.getByRole("button", { name: "Buscar servicios" }).click();
  await expect(page.getByText("2 resultados", { exact: true })).toBeVisible();
});

test("result cards fall back when a provider has no description or location", async ({ page }) => {
  await page.route("**/api/services?*", (route) => route.fulfill({
    json: {
      items: [
        serviceItem(1, {
          providerName: "Prestador sin datos",
          description: "",
          location: null,
          services: [
            { serviceTypeId: "service-type-1", name: "Mudanzas" },
            { serviceTypeId: "service-type-2", name: "Fletes" },
          ],
        }),
      ],
      total: 1,
      limit: 20,
      offset: 0,
    },
  }));

  await page.goto("/servicios");
  const card = page.locator(".service-result-card");
  await expect(card.getByRole("heading", { name: "Prestador sin datos" })).toBeVisible();
  await expect(card.getByText("El prestador no agregó una descripción.")).toBeVisible();
  await expect(card.locator(".service-result-location")).toHaveCount(0);
  await expect(card.locator(".service-result-category")).toHaveText("Mudanzas · Fletes");
});

test("result card profile link encodes the provider identifier in its path", async ({ page }) => {
  await page.route("**/api/services?*", (route) => route.fulfill({
    json: { items: [serviceItem(1, { profileId: "perfil con espacio/1" })], total: 1, limit: 20, offset: 0 },
  }));

  await page.goto("/servicios");
  await expect(page.locator(".service-result-card").getByRole("link", { name: "Ver perfil" }))
    .toHaveAttribute("href", "/prestadores/perfil%20con%20espacio%2F1");
});

test("quote button stays disabled for a provider without published services", async ({ page }) => {
  await page.route("**/api/services?*", (route) => route.fulfill({
    json: { items: [serviceItem(1, { services: [] })], total: 1, limit: 20, offset: 0 },
  }));

  await page.goto("/servicios");
  const card = page.locator(".service-result-card");
  await expect(card.getByRole("button", { name: "Cotizar" })).toBeDisabled();
  await expect(card.getByRole("link", { name: "Ver perfil" })).toBeVisible();
});

test("first search request sends only the paging parameters when no filter is set", async ({ page }) => {
  let requestedUrl = "";
  await page.route("**/api/services?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } });
  });

  await page.goto("/servicios");
  await expect(page.getByRole("heading", { name: "No encontramos servicios con esos filtros" })).toBeVisible();
  const query = new URL(requestedUrl).searchParams;
  expect([...query.keys()].sort()).toEqual(["limit", "offset"]);
  expect(query.get("limit")).toBe("20");
  expect(query.get("offset")).toBe("0");
});

test("pagination moves through pages of 20 and disables the edge buttons", async ({ page }) => {
  const total = 45;
  const requestedOffsets: string[] = [];
  await page.route("**/api/services?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? "0");
    requestedOffsets.push(String(offset));
    const size = Math.min(20, total - offset);
    const items = Array.from({ length: size }, (_, index) => serviceItem(offset + index + 1));
    await route.fulfill({ json: { items, total, limit: 20, offset } });
  });

  await page.goto("/servicios");
  const pagination = page.getByRole("navigation", { name: "Páginas de resultados" });
  await expect(pagination.getByText("Resultados 1–20 de 45")).toBeVisible();
  await expect(pagination.getByRole("button", { name: "Anterior" })).toBeDisabled();
  await expect(pagination.getByRole("button", { name: "Siguiente" })).toBeEnabled();

  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination.getByText("Resultados 21–40 de 45")).toBeVisible();
  await expect(pagination.getByRole("button", { name: "Anterior" })).toBeEnabled();

  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination.getByText("Resultados 41–45 de 45")).toBeVisible();
  await expect(pagination.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Prestador de página 45" })).toBeVisible();

  await pagination.getByRole("button", { name: "Anterior" }).click();
  await expect(pagination.getByText("Resultados 21–40 de 45")).toBeVisible();
  // Going back reuses the cached page (staleTime 30s), and the first page may be requested twice on mount in dev,
  // so assert the pages that were reached rather than an exact request list.
  expect(requestedOffsets).toEqual(expect.arrayContaining(["0", "20", "40"]));
});

test("pagination controls are hidden when all results fit on one page", async ({ page }) => {
  await page.route("**/api/services?*", (route) => route.fulfill({
    json: { items: [serviceItem(1)], total: 20, limit: 20, offset: 0 },
  }));

  await page.goto("/servicios");
  await expect(page.getByRole("heading", { name: "Prestador de página 1" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Páginas de resultados" })).toHaveCount(0);
});

test("a new search from a later page returns to the first page of results", async ({ page }) => {
  const requestedOffsets: string[] = [];
  await page.route("**/api/services?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? "0");
    requestedOffsets.push(String(offset));
    const items = Array.from({ length: 20 }, (_, index) => serviceItem(offset + index + 1));
    await route.fulfill({ json: { items, total: 45, limit: 20, offset } });
  });

  await page.goto("/servicios");
  const pagination = page.getByRole("navigation", { name: "Páginas de resultados" });
  await pagination.getByRole("button", { name: "Siguiente" }).click();
  await expect(pagination.getByText("Resultados 21–40 de 45")).toBeVisible();

  await page.getByLabel("Buscar por servicio o prestador").fill("grúa");
  await page.getByRole("button", { name: "Buscar servicios" }).click();
  await expect(pagination.getByText("Resultados 1–20 de 45")).toBeVisible();
  expect(requestedOffsets).toContain("20");
  expect(requestedOffsets.at(-1)).toBe("0");
});

test("category error keeps the search usable without a category filter", async ({ page }) => {
  await page.route("**/api/service-types", (route) => route.abort());
  let requestedUrl = "";
  await page.route("**/api/services?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({ json: { items: [serviceItem(1)], total: 1, limit: 20, offset: 0 } });
  });

  await page.goto("/servicios");
  await expect(page.getByText("No pudimos cargar las categorías. Puedes buscar sin filtrar por categoría.")).toBeVisible();
  const category = page.getByLabel("Categoría");
  await expect(category.locator("option")).toHaveCount(1);
  await expect(category).toHaveValue("");

  await page.getByLabel("Buscar por servicio o prestador").fill("mudanza");
  await page.getByRole("button", { name: "Buscar servicios" }).click();
  await expect.poll(() => requestedUrl).toContain("q=mudanza");
  expect(new URL(requestedUrl).searchParams.has("serviceType")).toBe(false);
  await expect(page.getByRole("heading", { name: "Prestador de página 1" })).toBeVisible();
});

test("retry after a failed search loads the results", async ({ page }) => {
  let shouldFail = true;
  await page.route("**/api/services?*", async (route) => {
    if (shouldFail) {
      await route.abort();
      return;
    }
    await route.fulfill({ json: { items: [serviceItem(1)], total: 1, limit: 20, offset: 0 } });
  });

  await page.goto("/servicios");
  const errorState = page.locator(".marketplace-error");
  await expect(errorState.getByRole("heading", { name: "No pudimos cargar los servicios" })).toBeVisible();

  shouldFail = false;
  await errorState.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { name: "Prestador de página 1" })).toBeVisible();
  await expect(page.getByText("1 resultado", { exact: true })).toBeVisible();
  await expect(page.locator(".marketplace-error")).toHaveCount(0);
});

test("location filter without a commune sends only the region code", async ({ page }) => {
  let requestedUrl = "";
  await page.route("**/api/services?*", async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } });
  });

  await page.goto("/servicios?regionCode=13");
  await expect(page.getByLabel("Región")).toHaveValue("13");
  await expect(page.getByLabel("Comuna")).toBeEnabled();
  await expect.poll(() => requestedUrl).toContain("regionCode=13");
  const query = new URL(requestedUrl).searchParams;
  expect(query.get("regionCode")).toBe("13");
  expect(query.has("communeCode")).toBe(false);
});
