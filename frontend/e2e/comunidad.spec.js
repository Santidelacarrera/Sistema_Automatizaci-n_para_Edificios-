const { test, expect } = require("@playwright/test");

async function entrarComunidad(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("button", { name: "Conserjería" }).click();
  await page.getByRole("heading", { name: "Conserjería y comunidad" }).waitFor();
}

test("registra y entrega una encomienda con firma", async ({ page }) => {
  await entrarComunidad(page);
  await page.getByLabel("Departamento").selectOption({ index: 3 });
  await page.getByLabel("Transportista").fill("Starken");
  await page.getByRole("button", { name: "Registrar" }).click();
  await expect(page.getByRole("status").first()).toHaveText(/Encomienda registrada/);
  page.once("dialog", (d) => d.accept("Juan Pérez"));
  await page.getByRole("button", { name: "Entregar" }).first().click();
  await expect(page.getByText(/Retiró Juan Pérez/)).toBeVisible();
});

test("publica un comunicado en el muro", async ({ page }) => {
  await entrarComunidad(page);
  await page.getByLabel("Título").fill("Corte de agua");
  await page.getByLabel("Mensaje").fill("Martes de 9 a 13 h");
  await page.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByText("Corte de agua")).toBeVisible();
});

test("rechazar un aviso de pago exige motivo", async ({ page }) => {
  await entrarComunidad(page);
  page.once("dialog", (d) => d.accept("No aparece en la cartola"));
  await page.getByRole("button", { name: "Rechazar" }).first().click();
  await expect(page.getByText(/rechazado: No aparece en la cartola/)).toBeVisible();
});
