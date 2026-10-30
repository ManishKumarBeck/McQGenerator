import { choice, createTest, expect, startExam, test } from "./fixtures";

test("answers, review marks and position survive a page refresh", async ({ page, request }) => {
  const created = await createTest(request);
  await startExam(page, created.id);
  await choice(page, "4").click();
  await page.getByRole("button", { name: "Next" }).click();
  await choice(page, "9").click();
  await page.getByRole("button", { name: "Mark for review" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("All answers saved")).toBeVisible();
  const before = await page.getByTestId("timer").textContent();

  await page.reload();
  await expect(page.getByTestId("question-text")).toHaveText("What is 10 − 4?");
  const palette = page.getByRole("navigation", { name: "Question palette" });
  await expect(palette.getByRole("button", { name: "Question 1: Answered" })).toBeVisible();
  await expect(palette.getByRole("button", { name: "Question 2: Answered & marked" })).toBeVisible();
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(choice(page, "9")).toHaveAttribute("aria-checked", "true");
  // The timer continues from the server deadline rather than restarting.
  const after = await page.getByTestId("timer").textContent();
  expect(after! <= before!).toBeTruthy();
});

test("answers made while offline are queued and synced on reconnect", async ({ page, request, context }) => {
  const created = await createTest(request);
  const attemptId = await startExam(page, created.id);
  await expect(page.getByText("All answers saved")).toBeVisible();

  await context.setOffline(true);
  await choice(page, "4").click();
  await expect(page.getByText(/Offline — 1 change waiting/)).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await choice(page, "9").click();
  // Still selectable and navigable while offline.
  await expect(choice(page, "9")).toHaveAttribute("aria-checked", "true");

  // A manual retry while still offline keeps the changes queued.
  await page.getByRole("button", { name: /retry/ }).click();
  await expect(page.getByText(/Offline — 2 changes waiting/)).toBeVisible();

  await context.setOffline(false); // automatic retry with backoff picks them up
  await expect(page.getByText("All answers saved")).toBeVisible({ timeout: 20_000 });

  const session = await (await request.get(`/api/attempts/${attemptId}`)).json();
  expect(session.questions[0].selected_option).toBe(1);
  expect(session.questions[1].selected_option).toBe(1);
});

test("unsynced answers are restored from local backup after a reload", async ({ page, request, context }) => {
  const created = await createTest(request);
  const attemptId = await startExam(page, created.id);
  await expect(page.getByText("All answers saved")).toBeVisible();
  await context.setOffline(true);
  await choice(page, "5").click(); // wrong answer, chosen offline
  await expect(page.getByText(/Offline/)).toBeVisible();
  await context.setOffline(false);
  // Block the save so it can't sync before reload.
  await page.route("**/api/attempts/*/answers/*", (route) => route.abort());
  await page.reload();
  await page.unroute("**/api/attempts/*/answers/*");
  await expect(choice(page, "5")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("All answers saved")).toBeVisible({ timeout: 20_000 });
  const session = await (await request.get(`/api/attempts/${attemptId}`)).json();
  expect(session.questions[0].selected_option).toBe(2);
});

test("leaving the exam inside the app asks for confirmation", async ({ page, request }) => {
  const created = await createTest(request);
  await startExam(page, created.id);
  await page.getByRole("link", { name: "McqGen home" }).click();
  const dialog = page.getByRole("dialog", { name: "Leave the exam?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Stay" }).click();
  await expect(page).toHaveURL(/\/attempts\//);
  await page.getByRole("link", { name: "McqGen home" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Leave" }).click();
  await expect(page).toHaveURL(/\/$/);
  // The dashboard offers to resume.
  await expect(page.getByText("Continue where you left off")).toBeVisible();
});

test("the exam auto-submits when the timer runs out", async ({ page, request }) => {
  test.slow();
  const created = await createTest(request, { duration_minutes: 1 });
  await startExam(page, created.id);
  await choice(page, "4").click();
  await expect(page.getByText("All answers saved")).toBeVisible();
  // No user action: the countdown reaches zero and the client submits by itself.
  await page.waitForURL(/\/result$/, { timeout: 80_000 });
  await expect(page.getByText("Time ran out, so this test was submitted automatically")).toBeVisible();
  await expect(page.getByTestId("score-marks")).toContainText("4 / 16");
});

test("the server closes an abandoned attempt after its deadline", async ({ page, request }) => {
  test.slow();
  const created = await createTest(request, { duration_minutes: 1 });
  const attemptId = await startExam(page, created.id);
  await choice(page, "4").click();
  await expect(page.getByText("All answers saved")).toBeVisible();
  await page.goto("/history"); // leave the exam page; nobody submits it
  await page.waitForTimeout(64_000);
  const late = await request.put(`/api/attempts/${attemptId}/answers/1`, { data: { selected_option: 1 } });
  expect(late.status()).toBe(409);
  const result = await (await request.get(`/api/attempts/${attemptId}/result`)).json();
  expect(result.submit_reason).toBe("timeout");
  expect(result.score).toBe(4);
});
