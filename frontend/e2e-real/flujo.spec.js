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

test("reservas y finanzas contra el backend real: QR autenticado, quincho con tarifa, gastos y cartola", async ({ page }) => {
  await entrar(page);
  await expect(page.getByRole("grid")).toBeVisible();

  // visita: el QR es un PNG real que el servidor sólo entrega con sesión
  await page.getByRole("button", { name: "Reservas" }).click();
  await page.locator("#rv-depto").selectOption({ label: "102" });
  await page.getByLabel("Nombre de la visita").fill("Visita E2E");
  await page.getByRole("button", { name: "Reservar visita" }).click();
  const qr = page.getByRole("img", { name: /Código QR de la visita de Visita E2E/ });
  await expect(qr).toBeVisible();
  expect(await qr.evaluate((img) => img.naturalWidth)).toBeGreaterThan(50);

  // quincho: fuera de horario se rechaza con el motivo; dentro confirma y cobra la tarifa
  const dia = new Date(Date.now() + 5 * 86400000);
  const f = (h) => `${dia.getFullYear()}-${String(dia.getMonth() + 1).padStart(2, "0")}-${String(dia.getDate()).padStart(2, "0")}T${h}`;
  await page.locator("#re-esp").selectOption({ index: 1 });
  await page.locator("#re-depto").selectOption({ label: "103" });
  await page.locator("#re-ini").fill(f("06:00")); await page.locator("#re-fin").fill(f("08:00"));
  await page.getByRole("button", { name: "Reservar espacio" }).click();
  await expect(page.getByText(/Horario permitido: 10:00/)).toBeVisible();
  await page.locator("#re-ini").fill(f("12:00")); await page.locator("#re-fin").fill(f("16:00"));
  await page.getByRole("button", { name: "Reservar espacio" }).click();
  await expect(page.getByText(/tarifa de \$5\.000/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Cancelar reserva de Quincho/ })).toBeVisible();

  // gastos comunes: genera el mes y queda en la lista; un segundo intento del mismo mes se rechaza
  await page.getByRole("button", { name: "Finanzas" }).click();
  await page.getByLabel("Vence el").fill("2030-01-10");
  await page.getByLabel("Concepto").fill("Administración");
  await page.getByLabel("Monto total (CLP)").fill("600000");
  await page.getByRole("button", { name: "Revisar y generar" }).click();
  await page.getByRole("button", { name: "Sí, generar" }).click();
  await expect(page.getByText(/generados: \$600\.000 repartidos entre 6 departamentos/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Enviar el gasto común de/ })).toBeVisible();
  await page.getByLabel("Concepto").fill("Otra vez");
  await page.getByLabel("Monto total (CLP)").fill("1000");
  await page.getByRole("button", { name: "Revisar y generar" }).click();
  await page.getByRole("button", { name: "Sí, generar" }).click();
  await expect(page.getByText(/Ya se generaron gastos comunes/)).toBeVisible();

  // cartola: un pago con el código de cobro se concilia y otro sin datos queda sin identificar
  await page.getByRole("tab", { name: "Cartola bancaria" }).click();
  const csv = "fecha,descripcion,monto,id\n05/02/2026,TRANSF CC-E2EA-101 enero,50000,t1\n06/02/2026,Deposito desconocido,7000,t2\n";
  await page.locator("#ca-archivo").setInputFiles({ name: "cartola.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Conciliar" }).click();
  await expect(page.getByText(/pagos conciliados/)).toContainText("1");
  await expect(page.getByText("Deposito desconocido")).toBeVisible();
});
