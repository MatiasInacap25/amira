import type { Page } from "@playwright/test";

// Small sample of GET /api/locations (CUT codes). The real catalog has 16 regions and 346 communes.
export const locationsResponse = {
  regions: [
    { code: "05", name: "Valparaíso", communes: [{ code: "05101", name: "Valparaíso" }] },
    { code: "08", name: "Biobío", communes: [{ code: "08101", name: "Concepción" }] },
    { code: "13", name: "Metropolitana de Santiago", communes: [{ code: "13101", name: "Santiago" }, { code: "13114", name: "Puente Alto" }] },
  ],
};

// Sample of GET /api/service-types, using the slugs the backend ships.
export const serviceTypesResponse = {
  items: [
    { id: "service-type-1", slug: "mudanzas", name: "Mudanzas" },
    { id: "service-type-6", slug: "carga-compartida", name: "Carga compartida" },
    { id: "service-type-3", slug: "mercaderia", name: "Transporte de mercadería" },
    { id: "service-type-2", slug: "fletes", name: "Fletes y traslados" },
    { id: "service-type-4", slug: "escombros", name: "Recolección de escombros" },
    { id: "service-type-5", slug: "grua", name: "Servicios de grúa" },
  ],
};

export async function mockCatalogs(page: Page) {
  await page.route("**/api/locations", (route) => route.fulfill({ json: locationsResponse }));
  await page.route("**/api/service-types", (route) => route.fulfill({ json: serviceTypesResponse }));
}
