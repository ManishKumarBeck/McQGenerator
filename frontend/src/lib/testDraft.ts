import type { Difficulty, TestDetail, TestStatus, TestWrite } from "./types";

export const MIN_OPTIONS = 2;
export const MAX_OPTIONS = 6;

export interface DraftQuestion {
  key: string; // stable React key, also for new questions without an id
  id?: number;
  text: string;
  options: string[];
  correct_option: number;
  explanation: string;
  topic: string;
  source_ref: string;
}

export interface DraftTest {
  title: string;
  description: string;
  subject: string;
  topic: string;
  category: string;
  difficulty: Difficulty;
  duration_minutes: number | "";
  marks_per_question: number | "";
  negative_marks: number | "";
  shuffle_questions: boolean;
  shuffle_options: boolean;
  questions: DraftQuestion[];
}

let keyCounter = 0;
export const newKey = () => `q-${Date.now().toString(36)}-${(keyCounter++).toString(36)}`;

export function newQuestion(topic = ""): DraftQuestion {
  return { key: newKey(), text: "", options: ["", "", "", ""], correct_option: 0, explanation: "", topic, source_ref: "" };
}

export function emptyDraft(): DraftTest {
  return {
    title: "",
    description: "",
    subject: "",
    topic: "",
    category: "",
    difficulty: "medium",
    duration_minutes: 30,
    marks_per_question: 1,
    negative_marks: 0,
    shuffle_questions: false,
    shuffle_options: false,
    questions: [newQuestion()],
  };
}

export function draftFromTest(test: TestDetail): DraftTest {
  return {
    title: test.title,
    description: test.description,
    subject: test.subject,
    topic: test.topic,
    category: test.category,
    difficulty: test.difficulty,
    duration_minutes: test.duration_minutes,
    marks_per_question: test.marks_per_question,
    negative_marks: test.negative_marks,
    shuffle_questions: test.shuffle_questions,
    shuffle_options: test.shuffle_options,
    questions: test.questions.map((q) => ({
      key: `id-${q.id}`,
      id: q.id,
      text: q.text,
      options: [...q.options],
      correct_option: q.correct_option,
      explanation: q.explanation,
      topic: q.topic,
      source_ref: q.source_ref ?? "",
    })),
  };
}

export interface QuestionErrors {
  text?: string;
  options?: (string | undefined)[];
  general?: string;
}

export interface DraftErrors {
  fields: Partial<Record<"title" | "duration_minutes" | "marks_per_question" | "negative_marks" | "questions", string>>;
  questions: Record<string, QuestionErrors>;
  count: number;
}

const isNumber = (value: number | ""): value is number => value !== "" && Number.isFinite(value);

/** Mirrors the backend validation so problems are shown inline before saving. */
export function validateDraft(draft: DraftTest, { publishing }: { publishing: boolean }): DraftErrors {
  const fields: DraftErrors["fields"] = {};
  const questions: DraftErrors["questions"] = {};

  if (!draft.title.trim()) fields.title = "Give the test a title.";
  else if (draft.title.trim().length > 200) fields.title = "Keep the title under 200 characters.";

  const duration = draft.duration_minutes;
  if (!isNumber(duration) || !Number.isInteger(duration) || duration < 1 || duration > 600)
    fields.duration_minutes = "Enter a whole number of minutes between 1 and 600.";

  const marks = draft.marks_per_question;
  if (!isNumber(marks) || marks <= 0 || marks > 100) fields.marks_per_question = "Marks must be greater than 0 (max 100).";

  const negative = draft.negative_marks;
  if (!isNumber(negative) || negative < 0) fields.negative_marks = "Negative marks can't be below 0.";
  else if (isNumber(marks) && negative > marks) fields.negative_marks = "Can't exceed the marks for a correct answer.";

  if (publishing && draft.questions.length === 0) fields.questions = "Add at least one question before publishing.";

  for (const question of draft.questions) {
    const errors: QuestionErrors = {};
    if (!question.text.trim()) errors.text = "Question text is required.";
    const optionErrors = question.options.map((option, index) => {
      const value = option.trim();
      if (!value) return "Option can't be empty.";
      const firstIndex = question.options.findIndex((o) => o.trim().toLowerCase() === value.toLowerCase());
      if (firstIndex !== index) return "Duplicate option.";
      return undefined;
    });
    if (optionErrors.some(Boolean)) errors.options = optionErrors;
    if (question.options.length < MIN_OPTIONS) errors.general = `Add at least ${MIN_OPTIONS} options.`;
    else if (question.correct_option < 0 || question.correct_option >= question.options.length)
      errors.general = "Choose the correct option.";
    if (Object.keys(errors).length) questions[question.key] = errors;
  }

  return { fields, questions, count: Object.keys(fields).length + Object.keys(questions).length };
}

export function toPayload(draft: DraftTest, status: TestStatus): TestWrite {
  return {
    title: draft.title.trim(),
    description: draft.description.trim(),
    subject: draft.subject.trim(),
    topic: draft.topic.trim(),
    category: draft.category.trim(),
    difficulty: draft.difficulty,
    duration_minutes: Number(draft.duration_minutes),
    marks_per_question: Number(draft.marks_per_question),
    negative_marks: Number(draft.negative_marks),
    shuffle_questions: draft.shuffle_questions,
    shuffle_options: draft.shuffle_options,
    status,
    questions: draft.questions.map((q) => ({
      id: q.id ?? null,
      text: q.text.trim(),
      options: q.options.map((o) => o.trim()),
      correct_option: q.correct_option,
      explanation: q.explanation.trim(),
      topic: q.topic.trim(),
      source_ref: q.source_ref.trim(),
    })),
  };
}

/** Comparable snapshot of a draft (ignores React keys) for unsaved-change detection. */
export function draftFingerprint(draft: DraftTest): string {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  return JSON.stringify({ ...draft, questions: draft.questions.map(({ key, ...rest }) => rest) });
}
