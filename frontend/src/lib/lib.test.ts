import { describe, expect, it } from "vitest";
import { clockOffset, mergeBackup, paletteStatus, remainingSeconds, retryDelay, summarize, type AnswerMap } from "./exam";
import { formatClock, formatDuration, formatMarks, formatPercent, scoreTone } from "./format";
import { draftFingerprint, emptyDraft, newQuestion, toPayload, validateDraft } from "./testDraft";

describe("format", () => {
  it("formats countdown clocks", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(59.9)).toBe("0:59");
    expect(formatClock(605)).toBe("10:05");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(-5)).toBe("0:00");
  });

  it("formats durations, marks and percentages", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(150)).toBe("2m 30s");
    expect(formatDuration(3600)).toBe("1h");
    expect(formatDuration(null)).toBe("—");
    expect(formatMarks(4)).toBe("4");
    expect(formatMarks(0.25)).toBe("0.25");
    expect(formatMarks(-1.5)).toBe("−1.5");
    expect(formatPercent(18.75)).toBe("18.8%");
    expect(formatPercent(100)).toBe("100%");
    expect(formatPercent(null)).toBe("—");
  });

  it("maps scores to tones", () => {
    expect(scoreTone(80)).toBe("success");
    expect(scoreTone(50)).toBe("warning");
    expect(scoreTone(-10)).toBe("danger");
    expect(scoreTone(null)).toBe("neutral");
  });
});

describe("exam helpers", () => {
  const answers: AnswerMap = {
    0: { selected: 1, marked: false, timeSpent: 10 },
    1: { selected: null, marked: true, timeSpent: 3 },
    2: { selected: 0, marked: true, timeSpent: 0 },
    3: { selected: null, marked: false, timeSpent: 0 },
  };

  it("derives palette status", () => {
    expect(paletteStatus(answers[0], true)).toBe("answered");
    expect(paletteStatus(answers[1], true)).toBe("marked");
    expect(paletteStatus(answers[2], true)).toBe("answered-marked");
    expect(paletteStatus(answers[3], true)).toBe("unanswered");
    expect(paletteStatus(answers[3], false)).toBe("not-visited");
  });

  it("summarises progress", () => {
    expect(summarize(answers, 5)).toEqual({ total: 5, answered: 2, unanswered: 3, marked: 2 });
  });

  it("computes remaining time with server clock offset", () => {
    const now = Date.parse("2026-01-01T10:00:00Z");
    // Server clock is 30s ahead of the browser.
    const offset = clockOffset("2026-01-01T10:00:30Z", now - 100, now + 100);
    expect(offset).toBe(30_000);
    expect(remainingSeconds("2026-01-01T10:10:30Z", offset, now)).toBe(600);
    expect(remainingSeconds("2026-01-01T09:00:00Z", offset, now)).toBe(0);
    expect(clockOffset("garbage", now, now)).toBe(0);
  });

  it("backs off retries up to 15 seconds", () => {
    expect([0, 1, 2, 3, 4, 10].map(retryDelay)).toEqual([1000, 2000, 4000, 8000, 15000, 15000]);
  });

  it("merges only unsynced local answers over server state", () => {
    const server: AnswerMap = {
      0: { selected: 2, marked: false, timeSpent: 20 },
      1: { selected: null, marked: false, timeSpent: 0 },
    };
    const merged = mergeBackup(
      server,
      {
        answers: { 0: { selected: 0, marked: true, timeSpent: 5 }, 1: { selected: 3, marked: false, timeSpent: 9 } },
        pending: [1, 7],
        current: 1,
        visited: [0, 1, 9],
      },
      2,
    );
    expect(merged.answers[0].selected).toBe(2); // synced already: server wins
    expect(merged.answers[1]).toEqual({ selected: 3, marked: false, timeSpent: 9 });
    expect(merged.pending).toEqual([1]); // out-of-range position dropped
    expect(merged.current).toBe(1);
    expect([...merged.visited].sort()).toEqual([0, 1]);
  });

  it("handles a missing or corrupt backup", () => {
    const merged = mergeBackup({}, null, 3);
    expect(merged.current).toBe(0);
    expect(merged.pending).toEqual([]);
    expect(mergeBackup({}, { answers: {}, pending: [], current: 99, visited: [] }, 3).current).toBe(0);
  });
});

describe("test draft validation", () => {
  it("requires a title and complete questions", () => {
    const draft = emptyDraft();
    const errors = validateDraft(draft, { publishing: true });
    expect(errors.fields.title).toBeDefined();
    const q = errors.questions[draft.questions[0].key];
    expect(q.text).toBeDefined();
    expect(q.options).toHaveLength(4);
  });

  it("flags duplicate options and bad marking", () => {
    const draft = emptyDraft();
    draft.title = "T";
    draft.marks_per_question = 1;
    draft.negative_marks = 2;
    draft.questions[0] = { ...draft.questions[0], text: "Q?", options: ["a", "A ", "b"], correct_option: 0 };
    const errors = validateDraft(draft, { publishing: false });
    expect(errors.fields.negative_marks).toMatch(/exceed/);
    expect(errors.questions[draft.questions[0].key].options).toEqual([undefined, "Duplicate option.", undefined]);
  });

  it("allows saving an empty draft but not publishing it", () => {
    const draft = { ...emptyDraft(), title: "T", questions: [] };
    expect(validateDraft(draft, { publishing: false }).count).toBe(0);
    expect(validateDraft(draft, { publishing: true }).fields.questions).toBeDefined();
  });

  it("builds a trimmed API payload", () => {
    const draft = { ...emptyDraft(), title: "  Quiz  ", questions: [{ ...newQuestion(), text: " Q? ", options: [" x ", "y"], correct_option: 1 }] };
    const payload = toPayload(draft, "published");
    expect(payload.title).toBe("Quiz");
    expect(payload.questions[0]).toMatchObject({ id: null, text: "Q?", options: ["x", "y"], correct_option: 1 });
    expect(payload.status).toBe("published");
  });

  it("ignores React keys when detecting changes", () => {
    const a = emptyDraft();
    const b = { ...a, questions: a.questions.map((q) => ({ ...q, key: "other" })) };
    expect(draftFingerprint(a)).toBe(draftFingerprint(b));
    expect(draftFingerprint({ ...a, title: "x" })).not.toBe(draftFingerprint(a));
  });
});
