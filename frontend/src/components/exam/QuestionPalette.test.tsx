import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { summarize, type AnswerMap } from "../../lib/exam";
import { QuestionPalette } from "./QuestionPalette";

describe("QuestionPalette", () => {
  it("shows each question's status and navigates on click", async () => {
    const answers: AnswerMap = {
      0: { selected: 1, marked: false, timeSpent: 0 },
      1: { selected: null, marked: true, timeSpent: 0 },
      2: { selected: 2, marked: true, timeSpent: 0 },
    };
    const onSelect = vi.fn();
    render(
      <QuestionPalette total={4} answers={answers} visited={new Set([0, 1, 2])} current={1} summary={summarize(answers, 4)} onSelect={onSelect} />,
    );
    expect(screen.getByRole("button", { name: "Question 1: Answered" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Question 2: Marked for review" })).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("button", { name: "Question 3: Answered & marked" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Question 4: Not visited" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Question 4/ }));
    expect(onSelect).toHaveBeenCalledWith(3);
  });
});
