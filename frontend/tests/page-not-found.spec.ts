import { expect, test } from "@playwright/test";

const unknownRoute = "/esta-ruta-no-existe";

test("unknown routes return HTTP 404 with a Spanish not-found page", async ({ page }) => {
  const response = await page.goto(unknownRoute);

  expect(response?.status()).toBe(404);
  await expect(page).toHaveTitle("Página no encontrada | Amira");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByRole("heading", { level: 1, name: "Página no encontrada" })).toBeVisible();
  await expect(page.getByText("La página que buscas no existe o fue movida.")).toBeVisible();
});

test("not-found page links back home and to the service search", async ({ page }) => {
  await page.goto(unknownRoute);

  const content = page.locator("#contenido");
  await expect(content.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
  await expect(content.getByRole("link", { name: "Buscar servicios" })).toHaveAttribute("href", "/servicios");
});

test("not-found page keeps the site header and footer", async ({ page }) => {
  await page.goto(unknownRoute);

  await expect(page.getByRole("navigation", { name: "Navegación principal" })).toBeVisible();
  await expect(page.getByRole("contentinfo")).toBeVisible();
});

test("not-found page fits a phone viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(unknownRoute);

  const dimensions = await page.evaluate(() => ({
    body: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
