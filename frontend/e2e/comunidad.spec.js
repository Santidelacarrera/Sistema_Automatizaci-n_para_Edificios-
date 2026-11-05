const { test, expect } = require("@playwright/test");

async function ir(page, pestaña, titulo) {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: pestaña, exact: true }).click();
  await page.getByRole("heading", { name: titulo, level: 2 }).waitFor();
}

test("registra una encomienda y confirma la entrega en línea, sin diálogos del navegador", async ({ page }) => {
  await ir(page, "Conserjería", "Conserjería");
  await page.getByLabel("Departamento").selectOption({ index: 3 });
  await page.getByLabel("Transportista").fill("Starken");
  await page.getByRole("button", { name: "Registrar encomienda" }).click();
  await expect(page.getByRole("status").first()).toContainText("Encomienda registrada");
  await page.getByRole("button", { name: "Entregar" }).first().click();
  await expect(page.getByRole("button", { name: "Confirmar entrega" })).toBeDisabled();
  await page.getByLabel("Nombre de quien retira").fill("Juan Pérez");
  await page.getByRole("button", { name: "Confirmar entrega" }).click();
  await expect(page.getByText("Retiró Juan Pérez")).toBeVisible();
});

test("publica un comunicado y lo retira con confirmación", async ({ page }) => {
  await ir(page, "Conserjería", "Conserjería");
  await page.getByLabel("Título").fill("Corte de agua");
  await page.getByLabel("Mensaje", { exact: true }).fill("Martes de 9 a 13 h");
  await page.getByRole("button", { name: "Publicar comunicado" }).click();
  await expect(page.getByText("Corte de agua", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retirar" }).first().click();
  await expect(page.getByText(/¿Retirar «/)).toBeVisible();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByText(/¿Retirar «/)).toHaveCount(0);
});

test("rechazar un aviso de pago exige un motivo", async ({ page }) => {
  await ir(page, "Conserjería", "Conserjería");
  await page.getByRole("button", { name: "Rechazar" }).first().click();
  await expect(page.getByRole("button", { name: "Rechazar aviso" })).toBeDisabled();
  await page.getByLabel("Motivo del rechazo").fill("No aparece en la cartola");
  await page.getByRole("button", { name: "Rechazar aviso" }).click();
  await expect(page.getByText("No aparece en la cartola")).toBeVisible();
});

test("edita tarifa y aforo de un espacio común", async ({ page }) => {
  await ir(page, "Conserjería", "Conserjería");
  await page.getByRole("row", { name: /Quincho/ }).getByRole("button", { name: "Editar" }).click();
  await page.getByLabel("Aforo (0 = sin límite)").fill("12");
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByRole("status").first()).toContainText("tarifa y aforo guardados");
  await expect(page.getByRole("row", { name: /Quincho/ })).toContainText("12 personas");
});

test("finanzas: calcula gastos con fondo de reserva y muestra el total", async ({ page }) => {
  await ir(page, "Finanzas", "Finanzas");
  await expect(page.getByText("Departamentos morosos")).toBeVisible();
  await page.getByLabel("Vence el").fill("2026-12-10");
  await page.getByLabel("Concepto del gasto 1").fill("Administración");
  await page.getByLabel("Monto del gasto 1").fill("1000000");
  await page.getByRole("button", { name: "Calcular y cargar a los departamentos" }).click();
  await expect(page.getByRole("status").first()).toContainText("1.050.000");
});

test("finanzas: los intereses piden confirmación antes de cargarse", async ({ page }) => {
  await ir(page, "Finanzas", "Finanzas");
  await page.getByRole("button", { name: "Cargar intereses", exact: true }).click();
  await expect(page.getByText(/Se cargará 1.5 % sobre el capital vencido/)).toBeVisible();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByText(/Se cargará/)).toHaveCount(0);
});
