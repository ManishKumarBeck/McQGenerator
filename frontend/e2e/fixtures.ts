import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";

export interface QuestionInput {
  text: string;
  options: string[];
  correct_option: number;
  topic?: string;
  explanation?: string;
}

export const ARITHMETIC: QuestionInput[] = [
  { text: "What is 2 + 2?", options: ["3", "4", "5", "6"], correct_option: 1, topic: "Addition", explanation: "2 + 2 = 4" },
  { text: "What is 3 × 3?", options: ["6", "9", "12", "33"], correct_option: 1, topic: "Multiplication" },
  { text: "What is 10 − 4?", options: ["6", "7", "14", "4"], correct_option: 0, topic: "Subtraction" },
  { text: "What is 8 ÷ 2?", options: ["2", "4", "6", "16"], correct_option: 1, topic: "Division" },
];

export async function createTest(request: APIRequestContext, overrides: Record<string, unknown> = {}) {
  const response = await request.post("/api/tests", {
    data: {
      title: `Arithmetic ${Date.now()}`,
      subject: "Math",
      topic: "Arithmetic",
      difficulty: "easy",
      duration_minutes: 10,
      marks_per_question: 4,
      negative_marks: 1,
      status: "published",
      questions: ARITHMETIC,
      ...overrides,
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as { id: number; title: string };
}

export async function startExam(page: Page, testId: number) {
  await page.goto(`/tests/${testId}`);
  await page.getByRole("button", { name: "Start test" }).click();
  await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("question-text")).toBeVisible();
  return page.url().split("/").pop()!;
}

/** The answer option button whose visible text is exactly `text`. */
export const choice = (page: Page, text: string) =>
  page.getByRole("radiogroup").getByRole("radio").filter({ hasText: new RegExp(`^[A-F]?\\s*${escape(text)}$`) });

function escape(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Every test fails if the browser logs errors (expected network failures are ignored). */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
      page.on("console", (message) => {
        if (message.type() !== "error") return;
        const text = message.text();
        if (/Failed to load resource|net::ERR/.test(text)) return;
        errors.push(text);
      });
      page.on("dialog", (dialog) => void dialog.accept());
      await use(errors);
      expect(errors, "browser console errors").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
