import { defineConfig, devices } from "@playwright/test";

const appUrl = `http://127.0.0.1:${process.env.AMIRA_TEST_APP_PORT ?? "3179"}`;
const authUrl = `http://127.0.0.1:${process.env.AMIRA_TEST_AUTH_PORT ?? "54329"}`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: appUrl,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        },
      },
    },
  ],
  webServer: [
    {
      command: "node tests/support/fake-auth-server.mjs",
      url: `${authUrl}/__health`,
      reuseExistingServer: false,
      timeout: 15_000,
      env: { NODE_ENV: "test" },
    },
    {
      command: "node tests/support/start-test-app.mjs",
      url: appUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NODE_ENV: "development",
        NEXT_PUBLIC_SUPABASE_URL: authUrl,
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "test_publishable_key_only",
        NEXT_PUBLIC_API_URL: authUrl,
        NEXT_PUBLIC_APP_ENV: "development",
      },
    },
  ],
});
