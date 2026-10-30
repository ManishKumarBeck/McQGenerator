// Types mirroring the backend Pydantic schemas (backend/app/schemas.py).

export type Difficulty = "easy" | "medium" | "hard" | "mixed";
export type TestStatus = "draft" | "published";
export type AttemptStatus = "in_progress" | "submitted";
export type SubmitReason = "manual" | "timeout";

export interface Question {
  id: number;
  position: number;
  text: string;
  options: string[];
  correct_option: number;
  explanation: string;
  topic: string;
}

export interface QuestionInput {
  id?: number | null;
  text: string;
  options: string[];
  correct_option: number;
  explanation: string;
  topic: string;
}

export interface TestSettings {
  title: string;
  description: string;
  subject: string;
  topic: string;
  category: string;
  difficulty: Difficulty;
  duration_minutes: number;
  marks_per_question: number;
  negative_marks: number;
  shuffle_questions: boolean;
  shuffle_options: boolean;
}

export interface TestWrite extends TestSettings {
  status: TestStatus;
  questions: QuestionInput[];
}

export interface TestSummary {
  id: number;
  title: string;
  description: string;
  subject: string;
  topic: string;
  category: string;
  difficulty: Difficulty;
  duration_minutes: number;
  marks_per_question: number;
  negative_marks: number;
  status: TestStatus;
  source: "ai" | "manual" | string;
  question_count: number;
  attempt_count: number;
  best_percentage: number | null;
  last_attempt_at: string | null;
  in_progress_attempt_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TestDetail extends TestSummary {
  shuffle_questions: boolean;
  shuffle_options: boolean;
  generation_notes: string;
  questions: Question[];
}

export interface GenerateTestResponse {
  test: TestDetail;
  warnings: string[];
}

export interface GenerateTestInput {
  title?: string;
  subject: string;
  topic: string;
  category: string;
  difficulty: Difficulty;
  question_count: number;
  source_text: string;
  instructions: string;
  duration_minutes?: number | null;
  marks_per_question: number;
  negative_marks: number;
  quality_review: boolean;
  file?: File | null;
}

export interface AttemptSummary {
  id: string;
  test_id: number | null;
  test_title: string;
  subject: string;
  topic: string;
  category: string;
  difficulty: string;
  status: AttemptStatus;
  submit_reason: SubmitReason | null;
  duration_seconds: number;
  marks_per_question: number;
  negative_marks: number;
  started_at: string;
  deadline_at: string;
  submitted_at: string | null;
  score: number | null;
  max_score: number;
  percentage: number | null;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
  question_count: number;
  time_spent_seconds: number | null;
}

export interface AttemptQuestion {
  position: number;
  text: string;
  options: string[];
  topic: string;
  selected_option: number | null;
  marked_for_review: boolean;
  time_spent_seconds: number;
}

export interface AttemptSession extends AttemptSummary {
  server_time: string;
  questions: AttemptQuestion[];
}

export interface AnswerUpdate {
  selected_option: number | null;
  marked_for_review: boolean;
  time_spent_seconds: number;
}

export interface AnswerSaved extends AnswerUpdate {
  position: number;
  server_time: string;
}

export interface TopicStat {
  topic: string;
  total: number;
  correct: number;
  incorrect: number;
  unanswered: number;
  accuracy: number | null;
}

export interface ResultQuestion {
  position: number;
  text: string;
  options: string[];
  correct_option: number;
  selected_option: number | null;
  is_correct: boolean | null;
  marks_awarded: number;
  marked_for_review: boolean;
  explanation: string;
  topic: string;
  time_spent_seconds: number;
}

export interface AttemptResult extends AttemptSummary {
  accuracy: number | null;
  negative_marks_total: number;
  topic_breakdown: TopicStat[];
  questions: ResultQuestion[];
  already_submitted: boolean;
}

export interface AnalyticsOverview {
  summary: {
    total_attempts: number;
    tests_taken: number;
    in_progress_attempts: number;
    average_percentage: number | null;
    best_percentage: number | null;
    accuracy: number | null;
    total_correct: number;
    total_incorrect: number;
    total_unanswered: number;
    total_time_seconds: number;
    average_time_per_question_seconds: number | null;
  };
  topics: TopicStat[];
  subjects: { subject: string; attempts: number; average_percentage: number | null }[];
  trend: { attempt_id: string; test_title: string; submitted_at: string; percentage: number }[];
  recent_attempts: AttemptSummary[];
}

export interface HealthStatus {
  status: "ok";
  database: boolean;
  ai_configured: boolean;
  model: string;
}
