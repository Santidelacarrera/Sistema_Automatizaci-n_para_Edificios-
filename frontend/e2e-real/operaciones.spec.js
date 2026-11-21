const { test, expect } = require("@playwright/test");
const API = process.env.E2E_API;
const PASS = process.env.E2E_PASSWORD;
const ED = process.env.E2E_EDIFICIO;
test.skip(!PASS || !API, "Ejecutar con scripts/e2e_local.py");

async function entrar(page, email = "admin@e2e.cl") {
  await page.goto("/");
  await page.getByLabel("Edificio", { exact: true }).fill(ED);
  await page.getByLabel("Correo", { exact: true }).fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(PASS);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}

test("residente reporta, administrador resuelve y residente lee la notificación", async ({ page, browser }) => {
  await entrar(page, "residente@e2e.cl");
  await page.getByLabel("Título de incidencia").fill("Fuga E2E de agua");
  await page.getByLabel("Descripción", { exact: true }).fill("Se detecta agua bajo la puerta de entrada.");
  await page.getByRole("button", { name: "Enviar incidencia" }).click();
  await expect(page.getByRole("button", { name: "Fuga E2E de agua", exact: true })).toBeVisible();
  const adminContext = await browser.newContext(); const admin = await adminContext.newPage();
  try {
    await entrar(admin);
    await admin.getByRole("button", { name: "Gestión comunitaria", exact: true }).click();
    await admin.getByRole("button", { name: "Incidencias", exact: true }).click();
    await admin.getByRole("button", { name: "Fuga E2E de agua", exact: true }).click();
    await admin.getByLabel("Estado", { exact: true }).selectOption("resuelta");
    await admin.getByRole("button", { name: "Guardar seguimiento" }).click();
    await expect(admin.getByRole("status")).toContainText("Cambios guardados");
    await page.getByRole("button", { name: "Notificaciones", exact: true }).click();
    await expect(page.getByText("Fuga E2E de agua: resuelta")).toBeVisible();
    await page.getByRole("button", { name: "Marcar como leída" }).last().click();
    await expect(page.getByText("Notificación marcada como leída.")).toBeVisible();
  } finally { await adminContext.close(); }
});

test("conserjería carga el panel sin solicitar cobranza", async ({ page }) => {
  const solicitudes = [];
  page.on("request", (r) => solicitudes.push(r.url()));
  await entrar(page, "conserje@e2e.cl");
  await expect(page.getByRole("grid")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cobranza", exact: true })).toHaveCount(0);
  expect(solicitudes.some((url) => url.endsWith("/cobranza"))).toBe(false);
  await page.getByRole("button", { name: "Conserjería", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Encomiendas|Conserjería/ }).first()).toBeVisible();
});

test("asamblea: padrón, asistencia, voto y acta con backend real", async ({ page, request, browser }) => {
  const login = await request.post(API + "/auth/login", { data: { edificio_id: ED, email: "admin@e2e.cl", password: PASS } });
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const residentes = await (await request.get(`${API}/edificios/${ED}/residentes`, { headers })).json();
  const residente = residentes.find((r) => r.email === "residente@e2e.cl");
  await entrar(page);
  await page.getByRole("button", { name: "Gestión comunitaria", exact: true }).click();
  await page.getByRole("button", { name: "Asambleas", exact: true }).click();
  await page.getByLabel("Título de asamblea").fill("Asamblea de prueba E2E");
  await page.getByLabel("Agenda", { exact: true }).fill("Resolver la propuesta de presupuesto.");
  await page.getByLabel("Fecha de asamblea").fill("2027-04-10T18:00");
  await page.getByRole("button", { name: "Crear borrador de asamblea" }).click();
  await page.getByRole("button", { name: "Asamblea de prueba E2E", exact: true }).click();
  await page.getByLabel("Representante autorizado").selectOption(String(residente.id));
  await page.getByRole("button", { name: "Agregar al padrón" }).click();
  await page.getByRole("button", { name: "Abrir votación y fijar padrón" }).click();
  const c = await browser.newContext(); const rp = await c.newPage();
  try {
    await entrar(rp, "residente@e2e.cl");
    await rp.getByRole("button", { name: "Asambleas", exact: true }).click();
    await rp.getByRole("button", { name: "Asamblea de prueba E2E", exact: true }).click();
    await rp.getByRole("button", { name: "Confirmar mi asistencia" }).click();
    await rp.getByLabel("A favor", { exact: true }).check();
    await rp.getByRole("button", { name: "Confirmar voto", exact: true }).click();
    await expect(rp.getByText("Recibo de su voto:")).toBeVisible();
    await page.getByLabel("Acta y acuerdos").fill("La propuesta queda aprobada en la consulta comunitaria.");
    await page.getByRole("button", { name: "Cerrar votación y guardar acta" }).click();
    await expect(page.getByRole("heading", { name: "Resultados", exact: true })).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: "A favor" })).toContainText("1");
  } finally { await c.close(); }
});

test("gestión responsive y accesibilidad básica con datos reales", async ({ page }) => {
  await entrar(page);
  await page.getByRole("button", { name: "Gestión comunitaria", exact: true }).click();
  await expect(page.getByText("Residentes activos", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Incidencias", exact: true }).click();
  await expect(page.getByLabel("Título de incidencia")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  const AxeBuilder = require("@axe-core/playwright").default;
  const resultado = await new AxeBuilder({ page }).include(".gestion-comunidad").analyze();
  expect(resultado.violations.filter((v) => ["serious", "critical"].includes(v.impact))).toEqual([]);
  await page.screenshot({ path: "../.artifacts/e2e/gestion-movil.png", fullPage: true });
});

test("contabilidad, personal y asistente IA con backend real", async ({ page }) => {
  await entrar(page);
  await page.getByRole("button", { name: "Gestión comunitaria", exact: true }).click();
  await page.getByRole("button", { name: "Contabilidad", exact: true }).click();
  await expect(page.getByText("Caja disponible")).toBeVisible();
  await page.getByLabel("Concepto").fill("Mantención eléctrica E2E");
  await page.getByLabel("Monto (CLP)").fill("45000");
  await page.getByRole("button", { name: "Registrar en libro contable" }).click();
  await expect(page.getByRole("status")).toContainText("Cambios guardados");

  await page.getByRole("button", { name: "Personal y comunidad", exact: true }).click();
  await page.getByLabel("Nombre completo").fill("Luis Conserje E2E");
  await page.getByLabel("RUT", { exact: true }).fill("12.345.678-5");
  await page.getByRole("button", { name: "Registrar trabajador" }).click();
  await expect(page.getByText("Luis Conserje E2E")).toBeVisible();

  await page.getByRole("button", { name: "Asistente IA", exact: true }).click();
  await expect(page.getByText("Proyección de caja a 30 días:")).toBeVisible();
  await page.getByLabel("Consulta administrativa o solicitud de borrador").fill("Genera un borrador de circular");
  await page.getByRole("button", { name: "Consultar asistente" }).click();
  await expect(page.getByText("Informativo operativo y financiero")).toBeVisible();

  await page.getByRole("button", { name: "Indexar conocimiento" }).click();
  await expect(page.getByText(/Base indexada:/)).toBeVisible();
  await page.getByLabel("Consulta administrativa o solicitud de borrador").fill("¿Cuántas unidades tiene el edificio?");
  await page.getByRole("button", { name: "Preguntar con memoria" }).click();
  await expect(page.getByText(/Modo:/)).toBeVisible();
});
