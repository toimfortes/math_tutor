import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("a student solves an extra-practice problem in a real browser", async ({ page }) => {
  await page.goto("/");

  // sign in (creates the account on first use)
  await page.getByPlaceholder("e.g. ada").fill("practicer");
  await page.locator('input[type="password"]').fill("pw");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 2 })).toBeVisible();

  // enter the separate extra-practice pool
  await page.getByRole("button", { name: "Extra practice" }).click();
  await expect(page.getByText("Generated practice problems")).toBeVisible();

  // items are served easiest-first, so the first rendered item may not be
  // bank.problems[0]; match the displayed prompt to find its canonical answer.
  const bank = JSON.parse(readFileSync(path.resolve("e2e/.artifacts/practice.json"), "utf-8"));
  const firstItem = page.locator(".practice-item").first();
  const shownPrompt = (await firstItem.locator("p").nth(1).textContent())?.trim();
  const matched = bank.problems.find((p: any) => p.neutral.prompt === shownPrompt);
  if (!matched) throw new Error(`could not match displayed prompt: ${shownPrompt}`);

  await firstItem.locator("input").fill(matched.neutral.canonical_answer);
  await firstItem.getByRole("button", { name: "Check" }).click();

  await expect(firstItem.locator(".practice-result.correct")).toBeVisible();
});
