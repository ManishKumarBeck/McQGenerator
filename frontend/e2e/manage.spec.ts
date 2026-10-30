import { createTest, expect, test } from "./fixtures";

test("create a test manually with validation and unsaved-change protection", async ({ page }) => {
  await page.goto("/tests/new/manual");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Give the test a title.")).toBeVisible();
  await expect(page.getByText("Question text is required.")).toBeVisible();

  await page.getByLabel("Title").fill("Capitals quiz");
  await page.getByLabel("Negative marks per wrong answer").fill("5");
  const q = page.getByTestId("question-editor").first();
  await q.getByLabel(/^Question/).fill("Capital of Japan?");
  await q.getByLabel("Option A", { exact: true }).fill("Tokyo");
  await q.getByLabel("Option B", { exact: true }).fill("Kyoto");
  await q.getByLabel("Option C", { exact: true }).fill("tokyo");
  await q.getByLabel("Option D", { exact: true }).fill("Osaka");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Can't exceed the marks for a correct answer.")).toBeVisible();
  await expect(page.getByText("Duplicate option.")).toBeVisible();

  await page.getByLabel("Negative marks per wrong answer").fill("0.25");
  await q.getByLabel("Option C", { exact: true }).fill("Nagoya");
  await q.getByRole("button", { name: "Remove option D" }).click();
  await expect(q.getByLabel("Option D", { exact: true })).toHaveCount(0);

  // Unsaved changes guard
  await page.getByRole("link", { name: "Tests", exact: true }).first().click();
  await expect(page.getByRole("dialog", { name: "Discard unsaved changes?" })).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Test published")).toBeVisible();
  await page.waitForURL(/\/tests\/\d+\/edit$/);
  await expect(page.getByText("All changes saved")).toBeVisible();

  // After saving, navigation is no longer blocked.
  await page.getByRole("link", { name: "Tests", exact: true }).first().click();
  await expect(page).toHaveURL(/\/tests$/);
  const card = page.getByTestId("test-card").filter({ hasText: "Capitals quiz" });
  await expect(card).toContainText("Published");
  await expect(card).toContainText("−0.25");
});

test("search, filter, duplicate and delete tests", async ({ page, request }) => {
  const stamp = Date.now();
  await createTest(request, { title: `Searchable algebra ${stamp}` });
  await createTest(request, { title: `Draft geometry ${stamp}`, status: "draft" });
  await page.goto("/tests");
  await page.getByLabel("Search tests").fill(`algebra ${stamp}`);
  await expect(page.getByTestId("test-card")).toHaveCount(1);
  await page.getByLabel("Search tests").fill(String(stamp));
  await expect(page.getByTestId("test-card")).toHaveCount(2);
  await page.getByRole("radio", { name: "Drafts" }).click();
  await expect(page.getByTestId("test-card")).toHaveCount(1);
  await expect(page.getByTestId("test-card")).toContainText("Review & publish");
  await page.getByRole("radio", { name: "All" }).click();

  const card = page.getByTestId("test-card").filter({ hasText: `Searchable algebra ${stamp}` });
  await card.getByRole("button", { name: /More actions/ }).click();
  await page.getByRole("menuitem", { name: "Duplicate" }).click();
  await page.waitForURL(/\/edit$/);
  await expect(page.getByLabel("Title")).toHaveValue(`Searchable algebra ${stamp} (copy)`);

  await page.goto("/tests");
  await page.getByLabel("Search tests").fill(`Draft geometry ${stamp}`);
  await expect(page.getByTestId("test-card")).toHaveCount(1);
  await page.getByTestId("test-card").getByRole("button", { name: /More actions/ }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete test" }).click();
  await expect(page.getByText("No matching tests")).toBeVisible();
});

test("AI generation errors are shown without losing the form", async ({ page }) => {
  await page.goto("/tests/new");
  await page.getByRole("button", { name: "Generate questions" }).click();
  await expect(page.getByText("Enter a subject or topic to generate from.")).toBeVisible();
  await page.getByLabel("Topic").fill("Please fail");
  await page.getByRole("button", { name: "Generate questions" }).click();
  await expect(page.getByText("OpenAI rate limit reached")).toBeVisible();
  await expect(page.getByLabel("Topic")).toHaveValue("Please fail");
  await expect(page).toHaveURL(/\/tests\/new$/);
});

test("generate from an uploaded text file", async ({ page }) => {
  await page.goto("/tests/new");
  await page.getByRole("radio", { name: "Upload file" }).click();
  await page.getByTestId("file-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Photosynthesis converts light energy into chemical energy in plants."),
  });
  await expect(page.getByText("notes.txt")).toBeVisible();
  await page.getByLabel("Number of questions").fill("2");
  await page.getByRole("button", { name: "Generate questions" }).click();
  await page.waitForURL(/\/edit$/);
  await expect(page.getByTestId("question-editor")).toHaveCount(2);
});

test("unknown pages and missing records show friendly errors", async ({ page }) => {
  await page.goto("/does-not-exist");
  await expect(page.getByText("Page not found")).toBeVisible();
  await page.goto("/tests/999999");
  await expect(page.getByText("Test not found.")).toBeVisible();
  await page.goto("/attempts/00000000-0000-0000-0000-000000000000");
  await expect(page.getByText("Couldn't open this exam")).toBeVisible();
});
