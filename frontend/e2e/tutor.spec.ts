import { expect, test } from "@playwright/test";

test("a student works the first problems in a real browser", async ({ page }) => {
  await page.goto("/");

  // Start a session (default theme is space_logistics).
  await page.getByRole("button", { name: "Start" }).first().click();

  // Problem 1 (lf_p01) uses the grid representation -> GridView paints an SVG.
  await expect(page.locator("svg.grid-view")).toBeVisible();
  await expect(page.getByRole("heading", { level: 2 })).toContainText("research station");
  await page.screenshot({ path: "e2e/screenshots/01-grid.png", fullPage: true });

  // Answer it: 4 km east, 3 km north -> (4, 3).
  await page.getByPlaceholder("Type your answer").fill("(4, 3)");
  await page.getByRole("button", { name: "Submit answer" }).click();

  // Problem 2 (lf_p02) uses the table representation -> TableView paints a table.
  await expect(page.locator("table.data-table")).toBeVisible();
  await expect(page.locator("table.data-table")).toContainText("Tanks");
  await page.screenshot({ path: "e2e/screenshots/02-table.png", fullPage: true });
});
