import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";

const user = {
  id: "company-user-1",
  aud: "authenticated",
  role: "authenticated",
  email: "empresa@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
};

const phoneFactor = { id: "factor-sms-1", factor_type: "phone", status: "verified", phone: "+56912345678" };
const vehiclesUrl = /\/api\/provider\/vehicles(\/[^?]*)?(\?.*)?$/;
const storageUrl = /https:\/\/storage\.example\.test\//;
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
};
const photoBuffer = readFileSync(path.resolve("tests/fixtures/chat-photo.png"));

type Vehicle = {
  vehicleId: string;
  plate: string;
  brand: string;
  model: string;
  year: number | null;
  maximumWeight: number | null;
  url: string;
  expiresAt: string;
};
type VehicleRequest = { method: string; path: string; contentType: string; body: string };

function accessToken(aal: "aal1" | "aal2", id = `${aal}-access-token`) {
  const payload = Buffer.from(JSON.stringify({ aal, exp: 2000000000, sub: user.id })).toString("base64url");
  return `eyJhbGciOiJub25lIn0.${payload}.${id}`;
}

function session(aal: "aal1" | "aal2" = "aal1", tokenId?: string, expiresIn = 3600) {
  return {
    access_token: accessToken(aal, tokenId),
    token_type: "bearer",
    expires_in: expiresIn,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    refresh_token: "refresh-test-token",
    user,
  };
}

function vehicle(overrides: Partial<Vehicle> = {}): Vehicle {
  return {
    vehicleId: "vehicle-1",
    plate: "ABCD12",
    brand: "Hyundai",
    model: "Porter",
    year: 2019,
    maximumWeight: 1200.5,
    url: `https://storage.example.test/vehicles/profile-1/vehicle-1.png?token=signed`,
    expiresAt: "2026-11-07T12:05:00.000Z",
    ...overrides,
  };
}

// Auth calls for the email/password, SMS MFA and session checks.
async function mockAuth(page: Page) {
  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const authPath = url.pathname.replace("/auth/v1", "");
    const method = request.method();

    if (authPath === "/token" && url.searchParams.get("grant_type") === "password") {
      await route.fulfill({ json: session("aal1", "password-aal1-token") });
      return;
    }
    if (authPath === "/user" && method === "GET") {
      await route.fulfill({ json: { ...user, factors: [phoneFactor] } });
      return;
    }
    if (authPath === "/factors" && method === "GET") {
      await route.fulfill({ json: { all: [phoneFactor], phone: [phoneFactor], totp: [] } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/challenge" && method === "POST") {
      await route.fulfill({ json: { id: "challenge-1", expires_at: Date.now() + 300000 } });
      return;
    }
    if (authPath === "/factors/factor-sms-1/verify" && method === "POST") {
      await route.fulfill({ json: session("aal2", "verified-aal2-token") });
      return;
    }
    await route.fulfill({ status: 404, json: { msg: `Unexpected fake Auth request: ${method} ${authPath}` } });
  });
}

// Signs in through the real login form with MFA completed, landing on /cuenta/vehiculos.
async function signInToVehicles(page: Page) {
  await mockAuth(page);
  await page.route("**/api/account/me", async (route) =>
    route.fulfill({ json: { user_id: "account-test-1", role: "company_owner", profile_id: "company-profile-1" } }));
  await page.goto("/login?next=%2Fcuenta%2Fvehiculos");
  await page.locator("#auth-email").fill(user.email);
  await page.locator("#auth-password").fill("un-password-seguro");
  await page.locator("form.auth-form button[type=submit]").click();
  await page.locator("#auth-code").fill("246810");
  await page.locator("form.auth-form button[type=submit]").click();
  await expect(page).toHaveURL(/\/cuenta\/vehiculos$/);
}

// Serves the vehicle list and mutates it like the backend does. Every call is recorded for assertions.
async function mockVehiclesApi(
  page: Page,
  options: { vehicles?: Vehicle[]; createStatus?: number; createDetail?: string } = {},
) {
  const vehicles = [...(options.vehicles ?? [])];
  const requests: VehicleRequest[] = [];
  await page.route(vehiclesUrl, async (route: Route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    const url = new URL(request.url());
    requests.push({
      method: request.method(),
      path: url.pathname,
      contentType: request.headers()["content-type"] ?? "",
      body: request.postData() ?? "",
    });

    if (request.method() === "GET") {
      await route.fulfill({ headers: corsHeaders, json: { items: vehicles } });
      return;
    }
    if (request.method() === "POST") {
      if (options.createStatus && options.createStatus !== 201) {
        await route.fulfill({ status: options.createStatus, headers: corsHeaders, json: { detail: options.createDetail ?? "" } });
        return;
      }
      const created = vehicle({ vehicleId: `vehicle-${vehicles.length + 1}`, plate: "ZXCV34", brand: "Toyota", model: "Hiace", year: null, maximumWeight: null });
      vehicles.push(created);
      await route.fulfill({ status: 201, headers: corsHeaders, json: { vehicleId: created.vehicleId } });
      return;
    }
    if (request.method() === "DELETE") {
      const id = url.pathname.split("/").pop() ?? "";
      const index = vehicles.findIndex((item) => item.vehicleId === id);
      if (index >= 0) vehicles.splice(index, 1);
      await route.fulfill({ status: index >= 0 ? 204 : 404, headers: corsHeaders });
      return;
    }
    await route.fulfill({ status: 405, headers: corsHeaders, json: { detail: "Method not allowed" } });
  });
  // The signed photo URLs point at the fake storage host; it serves the fixture photo.
  await page.route(storageUrl, async (route) => {
    await route.fulfill({ status: 200, contentType: "image/png", body: photoBuffer });
  });
  return { requests, vehicles };
}

async function fillForm(page: Page, fields: { plate?: string; brand?: string; model?: string; year?: string; weight?: string }) {
  await page.locator("#vehicle-plate").fill(fields.plate ?? "");
  await page.locator("#vehicle-brand").fill(fields.brand ?? "");
  await page.locator("#vehicle-model").fill(fields.model ?? "");
  await page.locator("#vehicle-year").fill(fields.year ?? "");
  await page.locator("#vehicle-maximum-weight").fill(fields.weight ?? "");
}

test.describe("cuenta vehiculos", () => {
  test("registers a vehicle with its photo and lists it", async ({ page }) => {
    const api = await mockVehiclesApi(page);
    await signInToVehicles(page);

    await fillForm(page, { plate: "zxcv 34", brand: "Toyota", model: "Hiace" });
    await page.locator("#vehicle-photo").setInputFiles({ name: "auto.png", mimeType: "image/png", buffer: photoBuffer });
    await page.getByRole("button", { name: "Registrar vehículo" }).click();

    await expect(page.getByRole("status")).toHaveText("Vehículo registrado.");
    const post = api.requests.find((entry) => entry.method === "POST");
    expect(post?.path).toBe("/api/provider/vehicles");
    expect(post?.contentType).toContain("multipart/form-data");
    expect(post?.body).toContain('name="plate"');
    expect(post?.body).toContain("zxcv 34");
    expect(post?.body).toContain('name="photo"; filename="auto.png"');
    await expect(page.getByRole("list", { name: "Vehículos registrados" }).getByRole("listitem")).toHaveCount(1);
    await expect(page.locator("#vehicle-plate")).toHaveValue("");
  });

  test("shows Spanish validation messages and sends nothing when the form is invalid", async ({ page }) => {
    const api = await mockVehiclesApi(page);
    await signInToVehicles(page);

    await page.getByRole("button", { name: "Registrar vehículo" }).click();
    await expect(page.locator("#vehicle-plate-error")).toHaveText("Ingresa la patente.");
    await expect(page.locator("#vehicle-brand-error")).toHaveText("Ingresa la marca.");
    await expect(page.locator("#vehicle-model-error")).toHaveText("Ingresa el modelo.");
    await expect(page.locator("#vehicle-photo-error")).toHaveText("Sube una foto del vehículo.");

    await fillForm(page, { plate: "ABCD12", brand: "Hyundai", model: "Porter", year: "1885", weight: "0" });
    await page.locator("#vehicle-photo").setInputFiles({ name: "auto.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
    await page.getByRole("button", { name: "Registrar vehículo" }).click();
    await expect(page.locator("#vehicle-year-error")).toHaveText("El año debe estar entre 1886 y 2200.");
    await expect(page.locator("#vehicle-maximum-weight-error")).toHaveText("El peso máximo debe ser mayor que 0 kg.");
    await expect(page.locator("#vehicle-photo-error")).toHaveText("La foto debe ser JPEG, PNG o WebP.");

    expect(api.requests.filter((entry) => entry.method === "POST")).toEqual([]);
  });

  test("shows the duplicate plate message from a 409 answer", async ({ page }) => {
    const api = await mockVehiclesApi(page, {
      createStatus: 409,
      createDetail: "Ya existe un vehículo registrado con esta patente.",
    });
    await signInToVehicles(page);

    await fillForm(page, { plate: "ABCD12", brand: "Hyundai", model: "Porter" });
    await page.locator("#vehicle-photo").setInputFiles({ name: "auto.png", mimeType: "image/png", buffer: photoBuffer });
    await page.getByRole("button", { name: "Registrar vehículo" }).click();

    // Next adds its own role="alert" route announcer, so the assertion targets the app's paragraph.
    await expect(page.locator("p.auth-error")).toHaveText("Ya existe un vehículo registrado con esta patente.");
    expect(api.requests.filter((entry) => entry.method === "POST")).toHaveLength(1);
  });

  test("lists the vehicles with their photo, alt text and details", async ({ page }) => {
    const api = await mockVehiclesApi(page, { vehicles: [vehicle()] });
    await signInToVehicles(page);

    const item = page.getByRole("list", { name: "Vehículos registrados" }).getByRole("listitem");
    await expect(item).toHaveCount(1);
    await expect(item).toContainText("ABCD12");
    await expect(item).toContainText("Hyundai Porter");
    await expect(item).toContainText("2019");
    await expect(item).toContainText("1200.5 kg");
    const photo = item.getByRole("img", { name: "Foto del vehículo ABCD12" });
    await expect(photo).toHaveAttribute("src", /storage\.example\.test\/vehicles\/profile-1\/vehicle-1\.png\?token=signed/);
    expect(api.requests.filter((entry) => entry.method === "GET")).not.toHaveLength(0);
  });

  test("deletes a vehicle from the list", async ({ page }) => {
    const api = await mockVehiclesApi(page, { vehicles: [vehicle()] });
    await signInToVehicles(page);

    await page.getByRole("button", { name: "Eliminar vehículo ABCD12" }).click();

    await expect(page.getByText("No tienes vehículos registrados todavía.")).toBeVisible();
    const deletion = api.requests.find((entry) => entry.method === "DELETE");
    expect(deletion?.path).toBe("/api/provider/vehicles/vehicle-1");
    expect(api.vehicles).toEqual([]);
  });
});
