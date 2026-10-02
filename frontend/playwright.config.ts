import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3179",
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
      url: "http://127.0.0.1:54329/__health",
      reuseExistingServer: false,
      timeout: 15_000,
      env: { NODE_ENV: "test" },
    },
    {
      command: "node tests/support/start-test-app.mjs",
      url: "http://127.0.0.1:3179",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NODE_ENV: "development",
        NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54329",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "test_publishable_key_only",
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8001",
      },
    },
  ],
});
