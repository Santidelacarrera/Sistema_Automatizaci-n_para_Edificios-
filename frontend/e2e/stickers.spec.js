const { test, expect } = require("@playwright/test");

async function entrarDemo(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: "Fachada" }).waitFor();
}

async function abrirDepto(page, numero) {
  await page.getByRole("gridcell", { name: new RegExp(`^Departamento ${numero}:`) }).click();
  await expect(page.getByRole("complementary", { name: `Departamento ${numero}` })).toBeVisible();
}

test("ficha: marcar un sticker como perdido cambia su estado", async ({ page }) => {
  await entrarDemo(page);
  await abrirDepto(page, "101");
  const drawer = page.getByRole("complementary", { name: "Departamento 101" });
  await drawer.getByRole("button", { name: "Marcar perdido el sticker 000000A1" }).click();
  await expect(page.getByRole("status")).toContainText("ya no abre");
  await expect(drawer.locator(".sticker-perdido").first()).toBeVisible();
});

test("ficha: reasignar un sticker a otro departamento", async ({ page }) => {
  await entrarDemo(page);
  await abrirDepto(page, "101");
  const drawer = page.getByRole("complementary", { name: "Departamento 101" });
  const formulario = drawer.locator("form.form-fila").first();
  await formulario.getByLabel("Reasignar a").selectOption({ label: "102" });
  await formulario.getByRole("button", { name: "Reasignar" }).click();
  await expect(page.getByRole("status")).toContainText("Sticker reasignado");
});

test("portón: cada lectura muestra su fuente y por qué no abrió", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Portón" }).click();
  await expect(page.locator(".fuente.sticker").first()).toBeVisible();
  await expect(page.getByText("Sticker perdido: no abre").first()).toBeVisible();
});

test("ajustes: elegir modo sticker y patente y guardar", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("button", { name: "Acceso", exact: true }).click();
  await page.getByRole("radio", { name: /Sticker y patente/ }).check();
  await page.getByRole("button", { name: "Guardar ajustes" }).click();
  await expect(page.getByRole("status")).toContainText("Ajustes guardados");
});

test("ajustes: valores fuera de rango se marcan antes de enviar", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("button", { name: "Acceso", exact: true }).click();
  await page.getByLabel("Ventana de coincidencia (segundos)").fill("500");
  await page.getByRole("button", { name: "Guardar ajustes" }).click();
  await expect(page.getByText("Entre 1 y 120 segundos.")).toBeVisible();
});

test("prueba de alcance: anota distancia y resultado en la bitácora", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("button", { name: "Prueba de alcance" }).click();
  await expect(page.getByRole("heading", { name: "Lecturas en vivo" })).toBeVisible();
  await page.getByLabel("Distancia (metros)").fill("4.5");
  await page.getByRole("radio", { name: "Leyó a veces" }).check();
  await page.getByRole("button", { name: "Anotar en la bitácora" }).click();
  await expect(page.getByRole("status")).toContainText("Anotado");
  await expect(page.getByRole("table").getByText("4,5 m")).toBeVisible();
});

test("prueba de alcance: sin distancia no anota", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("button", { name: "Prueba de alcance" }).click();
  await page.getByRole("button", { name: "Anotar en la bitácora" }).click();
  await expect(page.getByText("Indica la distancia en metros")).toBeVisible();
});

test("teclado: el foco llega a la navegación con borde visible", async ({ page }) => {
  await entrarDemo(page);
  await page.keyboard.press("Tab");
  const foco = page.locator(":focus");
  await expect(foco).toBeVisible();
  const borde = await foco.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(borde).not.toBe("none");
});

test("móvil: el portón no obliga a desplazarse en horizontal", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await entrarDemo(page);
  await page.getByRole("button", { name: "Portón" }).click();
  const desbordado = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(desbordado).toBe(false);
});

test("ajustes: generar clave nueva pide confirmación y la muestra una vez", async ({ page }) => {
  await entrarDemo(page);
  await page.getByRole("button", { name: "Administración" }).click();
  await page.getByRole("button", { name: "Acceso", exact: true }).click();
  await page.getByRole("button", { name: "Generar clave nueva" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("dejarán de abrir");
  await page.getByRole("button", { name: "Sí, generar clave nueva" }).click();
  await expect(page.locator(".clave-visible")).toContainText("demo-");
  await page.getByRole("button", { name: "Ya la guardé" }).click();
  await expect(page.locator(".clave-visible")).toHaveCount(0);
});
