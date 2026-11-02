const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

// Auditoría automática (axe, WCAG 2.1 A y AA) de cada pantalla del panel en modo demo.
// Sólo falla con problemas graves o críticos; los demás se listan en la salida para revisarlos.
async function auditar(page, nombre) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const graves = r.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  const resto = r.violations.filter((v) => !["serious", "critical"].includes(v.impact));
  if (resto.length) console.log(`[${nombre}] avisos menores: ${resto.map((v) => v.id).join(", ")}`);
  expect(graves.map((v) => `${v.id}: ${v.help} (${v.nodes.length} elementos, ej. ${v.nodes[0].target.join(" ")})`), `${nombre}`).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("inicio de sesión", async ({ page }) => { await auditar(page, "login"); });

for (const [nombre, boton] of [["fachada", null], ["portón", "Portón"], ["visitas", "Visitas"], ["reservas", "Reservas"], ["cobranza", "Cobranza"],
  ["finanzas", "Finanzas"], ["administración", "Administración"]]) {
  test(`pantalla ${nombre}`, async ({ page }) => {
    await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
    await page.getByRole("button", { name: "Reservas" }).waitFor();
    if (boton) await page.getByRole("button", { name: new RegExp(`^${boton}`) }).click();
    await page.waitForTimeout(400);
    await auditar(page, nombre);
  });
}

test("ficha de un departamento abierta", async ({ page }) => {
  await page.getByRole("button", { name: "Ver con datos de ejemplo" }).click();
  await page.getByRole("gridcell").first().click();
  await page.getByRole("complementary").waitFor();
  await auditar(page, "ficha");
});
