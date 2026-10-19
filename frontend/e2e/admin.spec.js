const { test, expect } = require("@playwright/test");

async function entrarDemo(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("heading", { name: "Administración" }).waitFor();
}

test("muestra un error de RUT junto al campo sin enviar", async ({ page }) => {
  await entrarDemo(page);
  await page.getByLabel("Nombre completo").fill("Prueba Vecina");
  await page.getByLabel("RUT", { exact: true }).fill("12.345.678-4");
  await page.getByLabel("Departamento").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Crear residente" }).click();
  await expect(page.getByText("RUT inválido")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText(/Revisa los campos marcados/);
});

test("crea un residente en demo y avisa", async ({ page }) => {
  await entrarDemo(page);
  await page.getByLabel("Nombre completo").fill("Prueba Vecina");
  await page.getByLabel("RUT", { exact: true }).fill("22.222.222-2");
  await page.getByLabel("Departamento").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Crear residente" }).click();
  await expect(page.getByRole("status")).toHaveText(/Residente creado/);
});

test("rechaza un RUT ya registrado con el motivo del servidor", async ({ page }) => {
  await entrarDemo(page);
  await page.getByLabel("Nombre completo").fill("Duplicada");
  await page.getByLabel("RUT", { exact: true }).fill("12.345.678-5"); // Ana Pérez en la demo
  await page.getByLabel("Departamento").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Crear residente" }).click();
  await expect(page.getByRole("status")).toContainText("ya está registrado");
});

test("valida horario de regla y UID de tag", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Reglas" }).click();
  await page.getByLabel("Tipo de regla").selectOption("horario");
  await page.getByLabel("Desde").fill("23:00");
  await page.getByLabel("Hasta", { exact: true }).fill("08:00");
  await page.getByRole("button", { name: "Crear regla" }).click();
  await expect(page.getByText("posterior a la de inicio")).toBeVisible();

  await page.getByRole("button", { name: "Tags RFID" }).click();
  await page.getByLabel("UID del tag").fill("XYZ");
  await page.getByRole("button", { name: "Registrar tag" }).click();
  await expect(page.getByText("entre 8 y 20")).toBeVisible();
});

test("la demo de cobranza dice que no envía mensajes", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: "Cobranza" }).click();
  await page.getByRole("button", { name: /Enviar a los/ }).click();
  await expect(page.getByRole("status")).toContainText("no envía");
});
