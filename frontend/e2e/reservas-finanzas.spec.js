const { test, expect } = require("@playwright/test");

async function entrarDemo(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: "Reservas" }).waitFor();
}

test("reservar una visita muestra su QR y valida los campos", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Reservas" }).click();
  await page.getByRole("button", { name: "Reservar visita" }).click();
  await expect(page.getByText("Elige el departamento que recibe la visita.")).toBeVisible();
  await page.getByLabel("Departamento").first().selectOption({ index: 1 });
  await page.getByLabel("Nombre de la visita").fill("Marcela Torres");
  await page.getByRole("button", { name: "Reservar visita" }).click();
  await expect(page.getByRole("img", { name: /Código QR de la visita de Marcela Torres/ })).toBeVisible();
});

test("reservar el quincho fuera de horario explica el motivo; dentro de horario confirma y se puede cancelar", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Reservas" }).click();
  await page.locator("#re-esp").selectOption({ index: 1 });
  await page.locator("#re-depto").selectOption({ index: 1 });
  const dia = new Date(Date.now() + 3 * 86400000); const f = (h) => `${dia.getFullYear()}-${String(dia.getMonth() + 1).padStart(2, "0")}-${String(dia.getDate()).padStart(2, "0")}T${h}`;
  await page.locator("#re-ini").fill(f("06:00")); await page.locator("#re-fin").fill(f("08:00"));
  await page.getByRole("button", { name: "Reservar espacio" }).click();
  await expect(page.getByText(/Horario permitido: 10:00/)).toBeVisible();
  await page.locator("#re-ini").fill(f("12:00")); await page.locator("#re-fin").fill(f("16:00"));
  await page.getByRole("button", { name: "Reservar espacio" }).click();
  await expect(page.getByText(/Reserva confirmada/)).toBeVisible();
  await page.getByRole("button", { name: /Cancelar reserva de Quincho/ }).click();
  await page.getByRole("button", { name: "Sí, cancelar" }).click();
  await expect(page.getByText(/Reserva cancelada/)).toBeVisible();
});

test("finanzas: generar gastos pide confirmación, muestra el total y deja el mes en la lista", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Finanzas" }).click();
  await page.getByRole("button", { name: "Revisar y generar" }).click();
  await expect(page.getByText("Indica la fecha de vencimiento.")).toBeVisible();
  await page.getByLabel("Vence el").fill("2030-01-10");
  await page.getByLabel("Concepto").fill("Administración");
  await page.getByLabel("Monto total (CLP)").fill("3600000");
  await page.getByRole("button", { name: "Revisar y generar" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("$3.600.000");
  await page.getByRole("button", { name: "Sí, generar" }).click();
  await expect(page.getByText(/Gastos de .* generados/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Enviar el gasto común de/ })).toBeVisible();
});

test("finanzas: la cartola sin archivo avisa y la circular valida asunto y mensaje", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Finanzas" }).click();
  await page.getByRole("tab", { name: "Cartola bancaria" }).click();
  await page.getByRole("button", { name: "Conciliar" }).click();
  await expect(page.getByText("Elige el archivo CSV de la cartola.")).toBeVisible();
  await page.getByRole("tab", { name: "Circular" }).click();
  await page.getByRole("button", { name: "Enviar a los residentes" }).click();
  await expect(page.getByText("Escribe el asunto.")).toBeVisible();
  await expect(page.getByText("Escribe el mensaje.")).toBeVisible();
});

test("móvil: reservas y finanzas no obligan a desplazarse en horizontal", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await entrarDemo(page);
  for (const nombre of ["Reservas", "Finanzas"]) {
    await page.getByRole("button", { name: nombre }).click();
    await page.waitForTimeout(200);
    const desborda = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(desborda, `${nombre} desborda en móvil`).toBe(false);
  }
});
