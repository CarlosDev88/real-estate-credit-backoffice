import { defineConfig, devices } from "@playwright/test";

// E2E contra el backend local (`docker compose up -d postgres backend`, :8000) con los
// datos de demo. El usuario de prueba sale de `.env.local` (E2E_USER_EMAIL y
// E2E_USER_PASSWORD), que no se versiona. Sin usuario, las pruebas se saltan.
try {
  process.loadEnvFile(".env.local");
} catch {
  // Sin `.env.local`: las pruebas que necesitan sesión se saltan con un mensaje.
}

const PORT = 3000;
export const BASE_URL = `http://localhost:${PORT}`;
export const AUTH_FILE = "test-results/.auth/advisor.json";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results/e2e",
  // Las pruebas cambian los datos de demo (aprueban y rechazan): una a la vez.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    locale: "es-CO",
    timezoneId: "America/Bogota",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "backoffice",
      testMatch: /backoffice\/.*\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    { name: "portal-setup", testMatch: /portal\/portal\.setup\.ts/, dependencies: ["setup"] },
    {
      name: "portal-mobile",
      testMatch: /e2e[\/]portal[\/].*\.spec\.ts/,
      dependencies: ["portal-setup"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true },
    },
    {
      name: "portal-desktop",
      testMatch: /e2e[\/]portal[\/].*\.spec\.ts/,
      dependencies: ["portal-setup"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  // Reutiliza `pnpm dev` si ya corre en :3000; si no, lo levanta.
  webServer: {
    command: "node ./node_modules/next/dist/bin/next dev --port 3000",
    url: `${BASE_URL}/login`,
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
