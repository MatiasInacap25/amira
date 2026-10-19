import { expect, test, type Page } from "@playwright/test";

const invitationKey = "amira-driver-invitation";
const validToken = "a".repeat(43);
const invitationPath = "/invitacion/conductor";

function landing(page: Page) {
  return page.locator("section.auth-form-panel");
}

test("returning visitor keeps the invitation when a valid token was retained", async ({ page }) => {
  await page.goto(`${invitationPath}#token=${validToken}`);
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toBeVisible();

  await page.goto(invitationPath);

  await expect(page.getByRole("heading", { name: "Únete a un equipo de Amira" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toBeVisible();
  await expect(landing(page).getByRole("alert")).toHaveCount(0);
  await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBe(validToken);
});

test("visitor without a token sees the unavailable message and a link to sign-in", async ({ page }) => {
  await page.goto(invitationPath);

  await expect(page.getByRole("heading", { name: "Únete a un equipo de Amira" })).toBeVisible();
  await expect(landing(page).getByRole("alert")).toHaveText("El enlace de invitación no es válido o ya no está disponible.");
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Crear cuenta desde la invitación" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Ir al inicio de sesión" })).toHaveAttribute("href", "/login");
});

test("malformed tokens show the unavailable message and clear a retained token", async ({ page }) => {
  await page.goto(`${invitationPath}#token=${validToken}`);
  await page.goto("/login");

  for (const badToken of ["a".repeat(31), `${"a".repeat(42)}!`]) {
    await page.goto(`${invitationPath}#token=${badToken}`);

    await expect(landing(page).getByRole("alert")).toHaveText("El enlace de invitación no es válido o ya no está disponible.");
    await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveCount(0);
    await expect(page).toHaveURL(invitationPath);
    await expect.poll(() => page.evaluate((key) => sessionStorage.getItem(key), invitationKey)).toBeNull();
    await page.goto("/login");
  }
});

test("unavailable state link leads to the sign-in page", async ({ page }) => {
  await page.goto(invitationPath);

  await page.getByRole("link", { name: "Ir al inicio de sesión" }).click();

  await expect(page).toHaveURL("/login");
  await expect(page.locator("#auth-email")).toBeVisible();
});

test("sign-in link from the invitation opens the login form with the acceptance return path", async ({ page }) => {
  await page.goto(`${invitationPath}#token=${validToken}`);

  await page.getByRole("link", { name: "Iniciar sesión" }).click();

  await expect(page).toHaveURL("/login?next=%2Finvitacion%2Fconductor%2Faceptar");
  await expect(page.locator("#auth-email")).toBeVisible();
});

test("invitation fits a 320px viewport without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto(`${invitationPath}#token=${validToken}`);
  await expect(page.getByRole("heading", { name: "Únete a un equipo de Amira" })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
});
