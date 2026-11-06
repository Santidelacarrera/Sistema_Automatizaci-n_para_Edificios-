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

test("finanzas: el fondo de reserva es opcional y parte en 0", async ({ page }) => {
  await ir(page, "Finanzas", "Finanzas");
  await expect(page.getByLabel("Fondo de reserva (%)")).toHaveValue("0");
});

test("finanzas: mora muestra el resumen y los intereses piden confirmación antes de cargarse", async ({ page }) => {
  await ir(page, "Finanzas", "Finanzas");
  await page.getByRole("tab", { name: "Mora e intereses" }).click();
  await expect(page.getByText("Departamentos morosos")).toBeVisible();
  await page.getByRole("button", { name: "Cargar intereses", exact: true }).click();
  await expect(page.getByText(/Se cargará 1.5 % sobre el capital vencido/)).toBeVisible();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByText(/Se cargará/)).toHaveCount(0);
});

test("mi depto: el portal muestra datos del departamento y permite avisar un pago", async ({ page }) => {
  await ir(page, "Mi Depto", "Mi depto");
  await expect(page.getByRole("heading", { name: "Gastos comunes", level: 3 })).toBeVisible();
  await page.getByLabel("Monto (CLP)").fill("50000");
  await page.getByLabel("Banco").fill("Banco Estado");
  await page.getByLabel("N.º de operación").fill("OP-778899");
  await page.getByRole("button", { name: "Avisar pago" }).click();
  await expect(page.getByRole("status").first()).toContainText("Aviso enviado");
});
