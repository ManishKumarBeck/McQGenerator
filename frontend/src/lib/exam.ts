import type { AttemptQuestion } from "./types";

export interface AnswerState {
  selected: number | null;
  marked: boolean;
  timeSpent: number; // seconds, may be fractional locally
}

export type AnswerMap = Record<number, AnswerState>;

export type PaletteStatus = "answered" | "unanswered" | "marked" | "answered-marked" | "not-visited";

export function answersFromQuestions(questions: AttemptQuestion[]): AnswerMap {
  const map: AnswerMap = {};
  for (const q of questions) {
    map[q.position] = { selected: q.selected_option, marked: q.marked_for_review, timeSpent: q.time_spent_seconds };
  }
  return map;
}

export function paletteStatus(answer: AnswerState | undefined, visited: boolean): PaletteStatus {
  if (!answer) return "not-visited";
  const answered = answer.selected !== null;
  if (answered && answer.marked) return "answered-marked";
  if (answer.marked) return "marked";
  if (answered) return "answered";
  return visited ? "unanswered" : "not-visited";
}

export interface ExamSummary {
  total: number;
  answered: number;
  unanswered: number;
  marked: number;
}

export function summarize(answers: AnswerMap, total: number): ExamSummary {
  let answered = 0;
  let marked = 0;
  for (let position = 0; position < total; position++) {
    const answer = answers[position];
    if (answer?.selected !== null && answer?.selected !== undefined) answered++;
    if (answer?.marked) marked++;
  }
  return { total, answered, unanswered: total - answered, marked };
}

/** Estimate server clock offset (ms) from a request's send/receive times and the server timestamp. */
export function clockOffset(serverTimeIso: string, sentAt: number, receivedAt: number): number {
  const server = Date.parse(serverTimeIso);
  if (Number.isNaN(server)) return 0;
  return server - (sentAt + receivedAt) / 2;
}

export function remainingSeconds(deadlineIso: string, offsetMs: number, now = Date.now()): number {
  return Math.max(0, (Date.parse(deadlineIso) - (now + offsetMs)) / 1000);
}

/** Exponential backoff for retrying failed saves: 1s, 2s, 4s … capped at 15s. */
export function retryDelay(attempt: number): number {
  return Math.min(15_000, 1000 * 2 ** Math.max(0, attempt));
}

// ---------------------------------------------------------------------------- local backup

export interface ExamBackup {
  answers: AnswerMap;
  pending: number[];
  current: number;
  visited: number[];
}

export const backupKey = (attemptId: string) => `exam:${attemptId}`;

/** Server state wins, except for positions the browser had not yet managed to save. */
export function mergeBackup(server: AnswerMap, backup: ExamBackup | null, total: number) {
  const answers: AnswerMap = { ...server };
  const pending: number[] = [];
  if (backup) {
    for (const position of backup.pending) {
      const local = backup.answers[position];
      if (local && position >= 0 && position < total) {
        answers[position] = {
          ...local,
          timeSpent: Math.max(local.timeSpent, server[position]?.timeSpent ?? 0),
        };
        pending.push(position);
      }
    }
  }
  const current = backup && backup.current >= 0 && backup.current < total ? backup.current : 0;
  const visited = new Set<number>((backup?.visited ?? []).filter((p) => p >= 0 && p < total));
  for (const [position, answer] of Object.entries(answers)) {
    if (answer.selected !== null || answer.marked || answer.timeSpent > 0) visited.add(Number(position));
  }
  visited.add(current);
  return { answers, pending, current, visited };
}
