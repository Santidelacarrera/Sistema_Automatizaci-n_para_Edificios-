const { test, expect } = require("@playwright/test");

const API = process.env.E2E_API || "http://localhost:8000";
const ED = process.env.E2E_EDIFICIO || "e2e_a";
const EMAIL = process.env.E2E_EMAIL || "admin@e2e.cl";
const PASS = process.env.E2E_PASSWORD;
const DEVICE_KEY = process.env.E2E_DEVICE_KEY;
const PATENTE = "BBCD12";

async function entrar(page, password = PASS) {
  await page.goto("/");
  await page.getByLabel("Edificio").fill(ED);
  await page.getByLabel("Correo").fill(EMAIL);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

test.skip(!PASS || !DEVICE_KEY, "Falta E2E_PASSWORD / E2E_DEVICE_KEY: use scripts/e2e_real.sh");

test("contraseña incorrecta muestra el error y no entra", async ({ page }) => {
  await entrar(page, "contraseña-equivocada-1");
  await expect(page.locator(".aviso.err")).toContainText(/inválid|incorrect/i);
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
});

test("recorrido: login, vehículo, lectura del portón y bitácora", async ({ page, request }) => {
  await entrar(page);
  await expect(page.getByRole("grid")).toBeVisible();

  // ficha del departamento 101 y alta de vehículo
  await page.getByRole("gridcell", { name: /Departamento 101/ }).click();
  await page.getByLabel("Patente").fill(PATENTE);
  await page.getByLabel("Vehículo").fill("Mazda 3 gris");
  await page.getByRole("button", { name: "Registrar vehículo" }).click();
  await expect(page.getByLabel(`Patente ${PATENTE}`).first()).toBeVisible();

  // lectura real contra el backend: patente registrada abre, desconocida no
  const url = `${API}/api/v1/${ED}/validar-acceso`;
  const h = { "X-Device-Key": DEVICE_KEY };
  const ok = await request.post(url, { headers: h, data: { edificio_id: ED, token_acceso: PATENTE, punto: "vehicular", tipo: "patente", confianza: 0.97 } });
  expect(ok.status()).toBe(200);
  const mal = await request.post(url, { headers: h, data: { edificio_id: ED, token_acceso: "ZZZZ99", punto: "vehicular", tipo: "patente", confianza: 0.97 } });
  expect(mal.status()).toBe(403);
  const sinClave = await request.post(url, { data: { edificio_id: ED, token_acceso: PATENTE, punto: "vehicular" } });
  expect(sinClave.status()).toBe(401);

  // la bitácora del panel refleja ambas lecturas
  await page.getByRole("button", { name: "Portón" }).click();
  await expect(page.locator(".pasadas .res", { hasText: /^Abrió$/ }).first()).toBeVisible();
  await expect(page.locator(".pasadas .res", { hasText: /^No abrió$/ }).first()).toBeVisible();
});

test("la sesión sin token es rechazada por la API y el panel vuelve al login", async ({ page }) => {
  await entrar(page);
  await expect(page.getByRole("grid")).toBeVisible();
  await page.evaluate(() => sessionStorage.setItem("sess", JSON.stringify({ token: "falso", edificio_id: "e2e_a", demo: false })));
  await page.reload();
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
});
