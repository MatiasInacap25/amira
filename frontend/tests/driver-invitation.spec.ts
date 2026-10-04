import { expect, test } from "@playwright/test";

test("driver invitation removes the token from the address bar and offers signup or sign-in", async ({ page }) => {
  const token = "a".repeat(43);
  await page.goto(`/invitacion/conductor#token=${token}`);

  await expect(page.getByRole("heading", { name: "Únete a un equipo de Amira" })).toBeVisible();
  await expect(page).toHaveURL("/invitacion/conductor");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("amira-driver-invitation"))).toBe(token);
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?next=%2Finvitacion%2Fconductor%2Faceptar");
  await page.getByRole("link", { name: "Crear cuenta desde la invitación" }).click();
  await expect(page).toHaveURL("/registro?intent=invite");
  await expect(page.getByLabel("Correo electrónico")).toBeVisible();
});
