import { choice, createTest, expect, startExam, test } from "./fixtures";

async function expectNoHorizontalScroll(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page should not scroll horizontally").toBeLessThanOrEqual(1);
  // Cards must also fit (content can be clipped without making the page scroll).
  const widest = await page.evaluate(() =>
    Math.max(0, ...Array.from(document.querySelectorAll("main .rounded-2xl")).map((el) => el.getBoundingClientRect().right)),
  );
  expect(widest, "cards should fit inside the viewport").toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth));
}

test("core pages fit a phone screen", async ({ page, request }) => {
  await createTest(request);
  const paths = ["/", "/tests", "/tests/new", "/tests/new/manual", "/library", "/history", "/analytics"];
  for (const width of [412, 360]) {
    await page.setViewportSize({ width, height: 800 });
    for (const path of paths) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await expectNoHorizontalScroll(page);
    }
  }
  await page.goto("/tests/new");
  await page.getByRole("radio", { name: "Library" }).click();
  await expectNoHorizontalScroll(page);
  await expect(page.getByRole("navigation", { name: "Main mobile" })).toBeVisible();
});

test("take an exam on a phone using the palette sheet", async ({ page, request }) => {
  const created = await createTest(request);
  await startExam(page, created.id);
  await expectNoHorizontalScroll(page);
  await choice(page, "4").click();
  await page.getByRole("button", { name: /1\/4 answered/ }).click();
  const sheet = page.getByRole("dialog", { name: "Questions" });
  await expect(sheet).toBeVisible();
  await sheet.getByRole("button", { name: /^Question 3/ }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByTestId("question-text")).toHaveText("What is 10 − 4?");
  await choice(page, "6").click();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit test" }).click();
  await page.waitForURL(/\/result$/);
  await expect(page.getByTestId("score-marks")).toContainText("8 / 16");
  await expectNoHorizontalScroll(page);
});
