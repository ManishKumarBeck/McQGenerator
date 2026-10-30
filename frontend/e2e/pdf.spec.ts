import { readFileSync } from "node:fs";
import { createTest, expect, test } from "./fixtures";

test("download a test as PDF with a custom heading", async ({ page, request }) => {
  const created = await createTest(request, { title: "Arithmetic Unit Test" });
  await page.goto(`/tests/${created.id}`);
  await page.getByRole("button", { name: "Download PDF" }).click();
  const dialog = page.getByRole("dialog", { name: "Download as PDF" });
  await expect(dialog.getByLabel("Test heading")).toHaveValue("Arithmetic Unit Test");
  await expect(dialog.getByLabel("Instructions")).toHaveValue(/4 multiple-choice questions/);

  await dialog.getByLabel("Institution / organisation").fill("Springfield High School");
  await dialog.getByLabel("Exam date").fill("12 Nov 2026");
  await dialog.getByLabel("Version label").fill("Set A");
  await dialog.getByRole("switch", { name: "Answer sheet" }).click();
  await dialog.getByRole("switch", { name: "Shuffle question order" }).click();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    dialog.getByRole("button", { name: "Download PDF" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^arithmetic-unit-test-seta-\d{4}-\d{2}-\d{2}\.pdf$/);
  const bytes = readFileSync(await download.path());
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(5_000);
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/Downloaded arithmetic-unit-test/)).toBeVisible();

  // The institution name is remembered for the next export (opened from the Tests page menu).
  await page.goto("/tests");
  const card = page.getByTestId("test-card").filter({ hasText: "Arithmetic Unit Test" }).first();
  await card.getByRole("button", { name: /More actions/ }).click();
  await page.getByRole("menuitem", { name: "Download PDF" }).click();
  await expect(page.getByRole("dialog").getByLabel("Institution / organisation")).toHaveValue("Springfield High School");
});
