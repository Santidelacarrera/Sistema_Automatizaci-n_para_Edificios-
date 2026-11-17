const { test, expect } = require("@playwright/test");
test.skip(!process.env.E2E_PASSWORD, "Requiere scripts/e2e_local.py");

async function entrar(page, email) {
  await page.goto("/");
  await page.getByLabel("Edificio", { exact: true }).fill(process.env.E2E_EDIFICIO);
  await page.getByLabel("Correo", { exact: true }).fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(process.env.E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}

test("cliente, plan, contrato y soporte entre administrador y operador SaaS", async ({ page, browser }) => {
  await entrar(page, "saas@e2e.cl");
  await page.getByRole("button", { name: "Administración SaaS", exact: true }).click();
  await page.getByLabel("Nombre del cliente").fill("Comunidad contrato E2E");
  await page.getByLabel("RUT del cliente").fill("12345678-5");
  await page.getByLabel("Correo de contacto").fill("contacto@example.cl");
  await page.getByRole("button", { name: "Registrar cliente", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Comunidad contrato E2E" })).toBeVisible();
  await page.getByLabel("Nombre del plan").fill("Plan E2E");
  await page.getByLabel("Precio mensual (CLP)").fill("25000");
  await page.getByLabel("Máximo de unidades").fill("6");
  await page.getByLabel("Máximo de residentes").fill("10");
  await page.getByLabel("Máximo de dispositivos").fill("2");
  await page.getByRole("button", { name: "Crear plan", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Plan E2E" })).toBeVisible();
  await page.getByRole("button", { name: "Suscripciones", exact: true }).click();
  await page.getByLabel("Edificio del contrato").selectOption(process.env.E2E_EDIFICIO);
  await page.getByLabel("Cliente del contrato").selectOption({ label: "Comunidad contrato E2E" });
  await page.getByLabel("Plan contratado").selectOption({ label: "Plan E2E" });
  await page.getByLabel("Estado del contrato").selectOption("activa");
  const hasta = new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10);
  await page.getByLabel("Vigente hasta").fill(hasta);
  await page.getByLabel("Motivo del contrato").fill("Contrato autorizado para prueba de flujo");
  await page.getByRole("button", { name: "Guardar contrato" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: process.env.E2E_EDIFICIO })).toContainText("Plan E2E");
  const ctx = await browser.newContext(); const admin = await ctx.newPage();
  try {
    await entrar(admin, "admin@e2e.cl");
    await admin.getByRole("button", { name: "Gestión comunitaria", exact: true }).click();
    await admin.getByRole("button", { name: "Mi suscripción", exact: true }).click();
    await expect(admin.getByText(/Plan E2E · activa/)).toBeVisible();
    await admin.getByRole("button", { name: "Soporte", exact: true }).click();
    await admin.getByLabel("Asunto de soporte").fill("Solicitud E2E de ampliación");
    await admin.getByLabel("Descripción de la solicitud").fill("Necesitamos ampliar las unidades del plan.");
    await admin.getByRole("button", { name: "Enviar solicitud", exact: true }).click();
    await expect(admin.getByRole("button", { name: "Solicitud E2E de ampliación", exact: true })).toBeVisible();
    // Recargar datos del operador para recibir el ticket creado en la otra sesión.
    await page.reload();
    await page.getByRole("button", { name: "Administración SaaS", exact: true }).click();
    await page.getByRole("button", { name: "Soporte", exact: true }).click();
    await page.getByRole("button", { name: "Solicitud E2E de ampliación", exact: true }).click();
    await page.getByLabel("Respuesta de soporte").fill("Solicitud recibida, revisaremos la ampliación.");
    await page.getByLabel("Estado de atención").selectOption("en_progreso");
    await page.getByRole("button", { name: "Enviar respuesta", exact: true }).click();
    await expect(page.getByRole("listitem").filter({ hasText: "Solicitud recibida" })).toBeVisible();
    await admin.getByRole("button", { name: "Solicitud E2E de ampliación", exact: true }).click();
    await expect(admin.getByText("Solicitud recibida, revisaremos la ampliación.")).toBeVisible();
  } finally { await ctx.close(); }
});
