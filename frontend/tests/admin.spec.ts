import { expect, test, type BrowserContext } from "@playwright/test";

for (const path of ["/admin", "/admin/auditoria"]) {
  test(`sign-in is required for ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin$|\/login\?next=\/admin$/);
  });
}


async function login(context: BrowserContext, admin: boolean) {
  const response = await context.request.get(`http://127.0.0.1:54329/__admin_session?admin=${admin}`);
  const value = Buffer.from(JSON.stringify(await response.json())).toString("base64url");
  await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${value}`, url: "http://127.0.0.1:3179" }]);
}

test("a signed-in non-admin sees the server-side denial", async ({ page, context }) => {
  await login(context, false);
  await page.goto("/admin/auditoria");
  await expect(page.getByRole("heading", { name: "No tienes acceso al panel de administración." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Volver a Amira" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("audit filters reach the backend and results link to their entity", async ({ page, context }) => {
  await login(context, true);
  await page.goto("/admin/auditoria");
  await page.getByLabel("Acción").fill("rating.hide");
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page).toHaveURL(/action=rating.hide/);
  await expect(page.getByRole("cell", { name: "rating.hide" })).toBeVisible();
  await expect(page.getByRole("link", { name: "rating: rating-1" })).toHaveAttribute("href", "/admin/valoraciones?detail=rating-1");
});
