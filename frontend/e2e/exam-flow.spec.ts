import { choice, createTest, expect, startExam, test } from "./fixtures";

test("generate with AI, review, publish, take and grade a test", async ({ page }) => {
  await page.goto("/tests/new");
  await page.getByLabel("Subject").fill("Mathematics");
  await page.getByLabel("Topic").fill("Addition");
  await page.getByLabel("Number of questions").fill("4");
  await page.getByLabel("Marks").fill("4");
  await page.getByLabel("Negative").fill("1");
  await page.getByRole("button", { name: "Generate questions" }).click();
  await expect(page.getByRole("button", { name: "Generating…" })).toBeVisible();

  await page.waitForURL(/\/tests\/\d+\/edit$/);
  await expect(page.getByTestId("question-editor")).toHaveCount(4);
  await expect(page.getByText("AI can make mistakes")).toBeVisible();

  // Edit: break a question, see validation, then fix it.
  const first = page.getByTestId("question-editor").first();
  await first.getByLabel(/^Question/).fill("");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Question text is required.")).toBeVisible();
  await expect(page.getByText("1 problem to fix")).toBeVisible();
  await first.getByLabel(/^Question/).fill("What is 2 + 3? (edited)");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Test published")).toBeVisible();
  await expect(page.getByText("All changes saved")).toBeVisible();

  await page.getByRole("link", { name: "View" }).click();
  await expect(page.getByText("Maximum score: 16")).toBeVisible();
  await page.getByRole("button", { name: "Start test" }).click();
  await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);

  // Q1 (2+3=5) correct via click, Q2 (3+4=7) wrong via keyboard, Q3 marked only, Q4 skipped.
  await expect(page.getByTestId("question-text")).toHaveText("What is 2 + 3? (edited)");
  await choice(page, "5").click();
  await expect(choice(page, "5")).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("question-text")).toHaveText("What is 3 + 4?");
  await page.keyboard.press("1"); // option A = 6, wrong
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Mark for review" }).click();
  await expect(page.getByText("Marked for review", { exact: true }).first()).toBeVisible();

  const palette = page.getByRole("navigation", { name: "Question palette" });
  await expect(palette.getByRole("button", { name: "Question 1: Answered" })).toBeVisible();
  await expect(palette.getByRole("button", { name: "Question 2: Answered" })).toBeVisible();
  await expect(palette.getByRole("button", { name: "Question 3: Marked for review" })).toBeVisible();
  await expect(palette.getByRole("button", { name: "Question 4: Not visited" })).toBeVisible();
  await expect(page.getByText("All answers saved")).toBeVisible();

  // Jump via palette, then submit with confirmation.
  await palette.getByRole("button", { name: /^Question 4/ }).click();
  await expect(page.getByTestId("question-text")).toHaveText("What is 5 + 6?");
  await page.getByRole("button", { name: "Review & submit" }).click();
  const dialog = page.getByRole("dialog", { name: "Submit your test?" });
  await expect(dialog).toContainText("2 unanswered questions");
  await dialog.getByRole("button", { name: "Keep working" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Review & submit" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit test" }).click();

  await page.waitForURL(/\/result$/);
  // +4 (correct) −1 (wrong) = 3 of 16 => 18.75%
  await expect(page.getByTestId("score-marks")).toContainText("3 / 16");
  await expect(page.getByTestId("score-percentage")).toHaveText("18.8%");
  await expect(page.locator('[data-testid="review-card"][data-status="correct"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="review-card"][data-status="incorrect"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="review-card"][data-status="unanswered"]')).toHaveCount(2);
  await page.getByRole("radio", { name: /^Wrong/ }).click();
  await expect(page.getByTestId("review-card")).toHaveCount(1);
  await expect(page.getByTestId("review-card")).toContainText("3 + 4 = 7.");

  // History and analytics reflect the attempt.
  await page.goto("/history");
  await expect(page.getByTestId("history-row").first()).toContainText("18.8%");
  await page.goto("/analytics");
  await expect(page.getByText("Tests completed")).toBeVisible();
  await expect(page.getByText("Score trend")).toBeVisible();
});

test("a submitted attempt cannot be reopened or resubmitted", async ({ page, request }) => {
  const created = await createTest(request);
  const attemptId = await startExam(page, created.id);
  await choice(page, "4").click();
  await expect(page.getByText("All answers saved")).toBeVisible();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit test" }).click();
  await page.waitForURL(/\/result$/);
  await expect(page.getByTestId("score-marks")).toContainText("4 / 16");

  // Going back to the exam URL lands on the result instead.
  await page.goto(`/attempts/${attemptId}`);
  await page.waitForURL(/\/result$/);

  // A duplicate submission from another tab returns the same, unchanged result.
  const again = await request.post(`/api/attempts/${attemptId}/submit`, {
    data: { reason: "manual", answers: [{ position: 1, selected_option: 1 }] },
  });
  const body = await again.json();
  expect(body.already_submitted).toBe(true);
  expect(body.score).toBe(4);
});

test("retake starts a fresh attempt from the result page", async ({ page, request }) => {
  const created = await createTest(request);
  const firstId = await startExam(page, created.id);
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit test" }).click();
  await page.waitForURL(/\/result$/);
  await expect(page.getByTestId("score-percentage")).toHaveText("0%");
  await page.getByRole("button", { name: "Retake test" }).click();
  await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
  expect(page.url()).not.toContain(firstId);
  await expect(choice(page, "4")).toHaveAttribute("aria-checked", "false");
});
