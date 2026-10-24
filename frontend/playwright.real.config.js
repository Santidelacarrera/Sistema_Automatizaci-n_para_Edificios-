// E2E del panel contra el BACKEND REAL (datos sembrados). Se lanza con scripts/e2e_real.sh,
// que levanta API + panel y exporta E2E_* con las credenciales de prueba.
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "e2e-real",
  timeout: 45000,
  workers: 1,
  use: {
    baseURL: process.env.PW_BASE_URL || "http://localhost:3000",
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
    trace: "retain-on-failure",
  },
});
