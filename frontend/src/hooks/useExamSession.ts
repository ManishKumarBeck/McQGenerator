import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { api, ApiError } from "../lib/api";
import {
  answersFromQuestions,
  backupKey,
  clockOffset,
  mergeBackup,
  remainingSeconds,
  retryDelay,
  type AnswerMap,
  type AnswerState,
  type ExamBackup,
} from "../lib/exam";
import { readJson, removeKey, writeJson } from "../lib/storage";
import type { AttemptSession, SubmitReason } from "../lib/types";

export type SyncState = "saved" | "saving" | "offline";
export type Phase = "loading" | "error" | "active" | "submitting" | "finished";

/** Minimum unsynced time on a question before a time-only update is sent. */
const TIME_SYNC_THRESHOLD = 5;

/**
 * Owns all state for an in-progress exam:
 * server-synchronised countdown, optimistic answers with a sequential autosave queue,
 * a localStorage backup for unsynced changes, and exactly-once submission.
 */
export function useExamSession(attemptId: string) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<unknown>(null);
  const [session, setSession] = useState<AttemptSession | null>(null);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [current, setCurrentState] = useState(0);
  const [visited, setVisited] = useState<Set<number>>(new Set());
  const [syncState, setSyncState] = useState<SyncState>("saved");
  const [pendingCount, setPendingCount] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitReason, setSubmitReason] = useState<SubmitReason | null>(null);

  // Refs mirror state for use inside async loops and timers.
  const answersRef = useRef<AnswerMap>({});
  const currentRef = useRef(0);
  const visitedRef = useRef<Set<number>>(new Set());
  const pendingRef = useRef<Set<number>>(new Set());
  const versionRef = useRef<Record<number, number>>({});
  const syncedTimeRef = useRef<Record<number, number>>({});
  const offsetRef = useRef(0);
  const deadlineRef = useRef<string | null>(null);
  const flushingRef = useRef(false);
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  const closedRef = useRef(false);
  const submittingRef = useRef(false);
  const lastTickRef = useRef<number>(0);
  const warnedRef = useRef<Set<number>>(new Set());
  const sessionDurationRef = useRef(0);

  // ------------------------------------------------------------------ persistence

  const persist = useCallback(() => {
    if (closedRef.current) return;
    const backup: ExamBackup = {
      answers: answersRef.current,
      pending: [...pendingRef.current],
      current: currentRef.current,
      visited: [...visitedRef.current],
    };
    writeJson(backupKey(attemptId), backup);
  }, [attemptId]);

  const commitAnswers = useCallback((next: AnswerMap) => {
    answersRef.current = next;
    setAnswers(next);
  }, []);

  // ------------------------------------------------------------------ finishing

  const goToResult = useCallback(
    (message?: string) => {
      if (closedRef.current) return;
      closedRef.current = true;
      if (retryTimerRef.current) window.clearTimeout(retryTimerRef.current);
      removeKey(backupKey(attemptId));
      setPhase("finished");
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      queryClient.invalidateQueries({ queryKey: ["attempts"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      if (message) toast.info(message);
      navigate(`/attempts/${attemptId}/result`, { replace: true });
    },
    [attemptId, navigate, queryClient],
  );

  // ------------------------------------------------------------------ autosave queue

  const flush = useCallback(async () => {
    if (flushingRef.current || closedRef.current || submittingRef.current) return;
    flushingRef.current = true;
    if (retryTimerRef.current) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    try {
      while (pendingRef.current.size > 0 && !closedRef.current && !submittingRef.current) {
        const position = pendingRef.current.values().next().value as number;
        const version = versionRef.current[position] ?? 0;
        const answer = answersRef.current[position];
        if (!answer) {
          pendingRef.current.delete(position);
          continue;
        }
        setSyncState("saving");
        const timeSpent = Math.round(answer.timeSpent);
        try {
          await api.saveAnswer(attemptId, position, {
            selected_option: answer.selected,
            marked_for_review: answer.marked,
            time_spent_seconds: timeSpent,
          });
          syncedTimeRef.current[position] = timeSpent;
          retryCountRef.current = 0;
          // Only clear if nothing changed while the request was in flight.
          if ((versionRef.current[position] ?? 0) === version) pendingRef.current.delete(position);
        } catch (error) {
          if (error instanceof ApiError && error.code === "attempt_closed") {
            goToResult("This attempt has already been submitted.");
            return;
          }
          if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
            pendingRef.current.delete(position);
            toast.error(`Couldn't save question ${position + 1}: ${error.message}`);
            continue;
          }
          // Network or server error: keep it pending and retry with backoff.
          setSyncState("offline");
          const delay = retryDelay(retryCountRef.current++);
          retryTimerRef.current = window.setTimeout(() => void flush(), delay);
          return;
        } finally {
          setPendingCount(pendingRef.current.size);
          persist();
        }
      }
      if (pendingRef.current.size === 0) setSyncState("saved");
    } finally {
      flushingRef.current = false;
    }
  }, [attemptId, goToResult, persist]);

  const enqueue = useCallback(
    (position: number) => {
      versionRef.current[position] = (versionRef.current[position] ?? 0) + 1;
      pendingRef.current.add(position);
      setPendingCount(pendingRef.current.size);
      persist();
      void flush();
    },
    [flush, persist],
  );

  // ------------------------------------------------------------------ submission

  const submit = useCallback(
    async (reason: SubmitReason) => {
      if (submittingRef.current || closedRef.current) return;
      submittingRef.current = true;
      setSubmitReason(reason);
      setSubmitError(null);
      setPhase("submitting");
      if (retryTimerRef.current) window.clearTimeout(retryTimerRef.current);

      const batch = Object.entries(answersRef.current).map(([position, a]) => ({
        position: Number(position),
        selected_option: a.selected,
        marked_for_review: a.marked,
        time_spent_seconds: Math.round(a.timeSpent),
      }));

      for (let attempt = 0; ; attempt++) {
        try {
          const result = await api.submitAttempt(attemptId, { reason, answers: batch });
          queryClient.setQueryData(["result", attemptId], result);
          goToResult(result.already_submitted ? "This attempt had already been submitted." : undefined);
          return;
        } catch (error) {
          const retriable = !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
          const message = error instanceof ApiError ? error.message : "Submission failed.";
          // A timed-out exam must be submitted: keep retrying. Manual submits let the user decide.
          if (reason === "timeout" && retriable && !closedRef.current) {
            setSubmitError(`${message} Retrying…`);
            await new Promise((resolve) => window.setTimeout(resolve, retryDelay(attempt)));
            continue;
          }
          submittingRef.current = false;
          setSubmitError(message);
          setPhase("active");
          toast.error(message);
          return;
        }
      }
    },
    [attemptId, goToResult, queryClient],
  );

  // ------------------------------------------------------------------ loading & time sync

  const applyServerClock = useCallback((data: AttemptSession, sentAt: number, receivedAt: number) => {
    offsetRef.current = clockOffset(data.server_time, sentAt, receivedAt);
    deadlineRef.current = data.deadline_at;
    setRemaining(remainingSeconds(data.deadline_at, offsetRef.current));
  }, []);

  // Latest callbacks for the one-time load effect (which must only re-run when the attempt changes).
  const callbacksRef = useRef({ flush, goToResult, applyServerClock, commitAnswers });
  useEffect(() => {
    callbacksRef.current = { flush, goToResult, applyServerClock, commitAnswers };
  });

  useEffect(() => {
    const { flush, goToResult, applyServerClock, commitAnswers } = callbacksRef.current;
    let cancelled = false;
    closedRef.current = false;
    submittingRef.current = false;
    const sentAt = Date.now();
    api
      .getAttempt(attemptId)
      .then((data) => {
        if (cancelled) return;
        if (data.status === "submitted") {
          goToResult();
          return;
        }
        applyServerClock(data, sentAt, Date.now());
        const backup = readJson<ExamBackup>(backupKey(attemptId));
        const merged = mergeBackup(answersFromQuestions(data.questions), backup, data.questions.length);
        for (const q of data.questions) syncedTimeRef.current[q.position] = q.time_spent_seconds;
        commitAnswers(merged.answers);
        currentRef.current = merged.current;
        setCurrentState(merged.current);
        visitedRef.current = merged.visited;
        setVisited(new Set(merged.visited));
        pendingRef.current = new Set(merged.pending);
        setPendingCount(merged.pending.length);
        sessionDurationRef.current = data.duration_seconds;
        setSession(data);
        setPhase("active");
        lastTickRef.current = Date.now();
        if (merged.pending.length) void flush();
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(error);
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  // Re-sync the clock (and detect server-side expiry) when the tab becomes visible again.
  useEffect(() => {
    if (phase !== "active") return;
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      const sentAt = Date.now();
      api
        .getAttempt(attemptId)
        .then((data) => {
          if (data.status === "submitted") goToResult("Time ran out while you were away. Your answers were submitted.");
          else applyServerClock(data, sentAt, Date.now());
        })
        .catch(() => undefined);
      void flush();
    };
    const onOnline = () => void flush();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onOnline);
    };
  }, [phase, attemptId, applyServerClock, flush, goToResult]);

  // Countdown tick: updates remaining time, per-question time, warnings and auto-submit.
  useEffect(() => {
    if (phase !== "active") return;
    const tick = () => {
      const now = Date.now();
      const elapsed = Math.min(5, Math.max(0, (now - lastTickRef.current) / 1000));
      lastTickRef.current = now;
      if (document.visibilityState === "visible") {
        const position = currentRef.current;
        const answer = answersRef.current[position];
        if (answer) answersRef.current = { ...answersRef.current, [position]: { ...answer, timeSpent: answer.timeSpent + elapsed } };
      }
      if (!deadlineRef.current) return;
      const left = remainingSeconds(deadlineRef.current, offsetRef.current, now);
      setRemaining(left);
      const duration = sessionDurationRef.current;
      for (const threshold of [300, 60]) {
        // Only warn for exams meaningfully longer than the threshold (no "5 minutes left" at the start of a 5-minute test).
        if (duration <= threshold + 60) continue;
        if (left <= threshold && left > threshold - 5 && !warnedRef.current.has(threshold)) {
          warnedRef.current.add(threshold);
          toast.warning(threshold === 300 ? "5 minutes remaining" : "1 minute remaining — the test will submit automatically");
        }
      }
      if (left <= 0) void submit("timeout");
    };
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [phase, submit]);

  // ------------------------------------------------------------------ user actions

  const updateAnswer = useCallback(
    (position: number, patch: Partial<AnswerState>) => {
      if (phase !== "active") return;
      const previous = answersRef.current[position] ?? { selected: null, marked: false, timeSpent: 0 };
      commitAnswers({ ...answersRef.current, [position]: { ...previous, ...patch } });
      enqueue(position);
    },
    [phase, commitAnswers, enqueue],
  );

  const setCurrent = useCallback(
    (next: number) => {
      const total = session?.questions.length ?? 0;
      if (next < 0 || next >= total || next === currentRef.current) return;
      const leaving = currentRef.current;
      const answer = answersRef.current[leaving];
      // Sync accumulated time for the question being left, if it is significant.
      if (answer && Math.round(answer.timeSpent) - (syncedTimeRef.current[leaving] ?? 0) >= TIME_SYNC_THRESHOLD) {
        enqueue(leaving);
      }
      currentRef.current = next;
      setCurrentState(next);
      visitedRef.current.add(next);
      setVisited(new Set(visitedRef.current));
      setAnswers(answersRef.current);
      persist();
    },
    [session, enqueue, persist],
  );

  const select = useCallback(
    (option: number | null) => updateAnswer(currentRef.current, { selected: option }),
    [updateAnswer],
  );

  const toggleMark = useCallback(() => {
    const answer = answersRef.current[currentRef.current];
    updateAnswer(currentRef.current, { marked: !answer?.marked });
  }, [updateAnswer]);

  return {
    phase,
    loadError,
    session,
    answers,
    current,
    visited,
    remaining,
    syncState,
    pendingCount,
    submitError,
    submitReason,
    setCurrent,
    select,
    toggleMark,
    submit,
    retrySave: flush,
  };
}
