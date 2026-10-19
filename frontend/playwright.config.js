// Pruebas E2E del panel en modo demo (no requiere backend).
// Local con Chrome instalado:  PW_CHANNEL=chrome npx playwright test
// Sin canal: npx playwright install chromium && npx playwright test
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "e2e",
  timeout: 30000,
  use: {
    baseURL: process.env.PW_BASE_URL || "http://localhost:3000",
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  webServer: process.env.PW_BASE_URL ? undefined : {
    command: "npm run build && npm run start",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 180000,
  },
});
