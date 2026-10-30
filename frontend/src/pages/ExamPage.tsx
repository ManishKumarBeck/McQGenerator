import clsx from "clsx";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, CloudOff, Eraser, Flag, Grid3X3, Loader2, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router";
import { ExamTimer } from "../components/exam/ExamTimer";
import { QuestionPalette } from "../components/exam/QuestionPalette";
import { Logo, ThemeToggle } from "../components/layout/AppLayout";
import { Button, ButtonLink } from "../components/ui/Button";
import { ConfirmDialog, Modal } from "../components/ui/Modal";
import { Alert, Badge, Card, ErrorState, Spinner } from "../components/ui/primitives";
import { useExamSession, type SyncState } from "../hooks/useExamSession";
import { useLeaveGuard } from "../hooks/useLeaveGuard";
import { summarize } from "../lib/exam";
import { OPTION_LABELS, pluralize } from "../lib/format";

export function ExamPage() {
  const { attemptId = "" } = useParams();
  const exam = useExamSession(attemptId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const total = exam.session?.questions.length ?? 0;
  const summary = useMemo(() => summarize(exam.answers, total), [exam.answers, total]);
  const active = exam.phase === "active";
  const blocker = useLeaveGuard(active || exam.phase === "submitting");

  const question = exam.session?.questions[exam.current];
  const answer = exam.answers[exam.current];

  // Keyboard shortcuts: 1-6/A-F choose, ←/→ navigate, M marks, Backspace clears.
  useEffect(() => {
    if (!active || confirmOpen || paletteOpen || blocker.state === "blocked") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const options = question?.options.length ?? 0;
      const key = event.key.toLowerCase();
      const numeric = Number(key);
      const letter = "abcdef".indexOf(key);
      if (numeric >= 1 && numeric <= options) exam.select(numeric - 1);
      else if (letter >= 0 && letter < options && key.length === 1) exam.select(letter);
      else if (key === "arrowright" || key === "n") exam.setCurrent(exam.current + 1);
      else if (key === "arrowleft" || key === "p") exam.setCurrent(exam.current - 1);
      else if (key === "m") exam.toggleMark();
      else if (key === "backspace" || key === "delete") exam.select(null);
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, confirmOpen, paletteOpen, blocker.state, question, exam]);

  if (exam.phase === "loading" || exam.phase === "finished") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label={exam.phase === "finished" ? "Opening your results…" : "Loading your exam…"} />
      </div>
    );
  }

  if (exam.phase === "error" || !exam.session || !question) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <ErrorState error={exam.loadError} title="Couldn't open this exam" onRetry={() => window.location.reload()} />
          <div className="pb-8 text-center">
            <ButtonLink to="/tests" variant="ghost">
              Back to tests
            </ButtonLink>
          </div>
        </Card>
      </div>
    );
  }

  const isLast = exam.current === total - 1;
  const goTo = (position: number) => {
    exam.setCurrent(position);
    setPaletteOpen(false);
  };

  const palette = (
    <QuestionPalette total={total} answers={exam.answers} visited={exam.visited} current={exam.current} summary={summary} onSelect={goTo} />
  );

  return (
    <div className="min-h-dvh bg-bg">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <div className="hidden sm:block">
            <Logo />
          </div>
          <div className="min-w-0 flex-1 sm:border-l sm:border-line sm:pl-4">
            <p className="truncate text-sm font-semibold" title={exam.session.test_title}>
              {exam.session.test_title}
            </p>
            <SyncIndicator state={exam.syncState} pending={exam.pendingCount} onRetry={() => void exam.retrySave()} />
          </div>
          <ExamTimer remaining={exam.remaining} total={exam.session.duration_seconds} />
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>
          <div className="hidden lg:block">
            <Button onClick={() => setConfirmOpen(true)} icon={<Send className="size-4" />} disabled={!active}>
              Submit
            </Button>
          </div>
        </div>
        <div className="h-1 bg-surface-2" aria-hidden>
          <div className="h-full bg-brand-500 transition-[width] duration-300" style={{ width: `${(summary.answered / total) * 100}%` }} />
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 pb-28 sm:px-6 lg:grid-cols-[1fr_300px] lg:pb-8">
        <section aria-labelledby="question-heading">
          {exam.submitError && (
            <Alert tone="danger" className="mb-4" icon={<AlertTriangle className="size-4" />} title="Submission failed">
              {exam.submitError} Your answers are saved — try submitting again.
            </Alert>
          )}
          <Card className="p-5 sm:p-7">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <h1 id="question-heading" className="text-sm font-semibold text-muted">
                Question {exam.current + 1} <span className="font-normal">of {total}</span>
              </h1>
              {question.topic && <Badge>{question.topic}</Badge>}
              {answer?.marked && (
                <Badge tone="brand" className="!border-violet-300 !bg-violet-50 !text-violet-700 dark:!border-violet-500/40 dark:!bg-violet-500/15 dark:!text-violet-300">
                  <Flag className="size-3" /> Marked for review
                </Badge>
              )}
            </div>
            <p className="text-lg leading-relaxed font-medium whitespace-pre-line text-fg sm:text-xl" data-testid="question-text">
              {question.text}
            </p>

            <div role="radiogroup" aria-labelledby="question-heading" className="mt-6 space-y-3">
              {question.options.map((option, index) => {
                const selected = answer?.selected === index;
                return (
                  <button
                    key={index}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    disabled={!active}
                    onClick={() => exam.select(index)}
                    className={clsx(
                      "flex w-full items-start gap-3 rounded-xl border-2 p-3.5 text-left transition-all sm:p-4",
                      selected
                        ? "border-brand-500 bg-brand-50 shadow-sm dark:bg-brand-500/15"
                        : "border-line bg-surface hover:border-brand-300 hover:bg-surface-2",
                    )}
                  >
                    <span
                      className={clsx(
                        "flex size-7 shrink-0 items-center justify-center rounded-lg text-sm font-semibold",
                        selected ? "bg-brand-600 text-white" : "bg-surface-2 text-muted",
                      )}
                    >
                      {selected ? <Check className="size-4" /> : OPTION_LABELS[index]}
                    </span>
                    <span className="pt-0.5 text-[15px] leading-relaxed text-fg">{option}</span>
                  </button>
                );
              })}
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-line pt-5">
              <Button
                variant={answer?.marked ? "secondary" : "outline"}
                size="sm"
                onClick={exam.toggleMark}
                disabled={!active}
                icon={<Flag className={clsx("size-4", answer?.marked && "fill-violet-500 text-violet-500")} />}
                aria-pressed={!!answer?.marked}
              >
                {answer?.marked ? "Unmark review" : "Mark for review"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => exam.select(null)} disabled={!active || answer?.selected === null} icon={<Eraser className="size-4" />}>
                Clear response
              </Button>
              <p className="ml-auto hidden text-xs text-muted md:block">Keys: 1–4 answer · ←/→ move · M mark</p>
            </div>
          </Card>

          <div className="mt-4 flex items-center justify-between gap-2">
            <Button variant="outline" onClick={() => exam.setCurrent(exam.current - 1)} disabled={exam.current === 0} icon={<ChevronLeft className="size-4" />}>
              Previous
            </Button>
            {isLast ? (
              <Button onClick={() => setConfirmOpen(true)} disabled={!active} icon={<Send className="size-4" />}>
                Review & submit
              </Button>
            ) : (
              <Button onClick={() => exam.setCurrent(exam.current + 1)}>
                Next <ChevronRight className="size-4" />
              </Button>
            )}
          </div>
        </section>

        <aside className="hidden lg:block">
          <Card className="sticky top-24 p-4">
            <h2 className="mb-3 text-sm font-semibold">Questions</h2>
            {palette}
          </Card>
        </aside>
      </main>

      {/* Mobile action bar */}
      <div className="fixed inset-x-0 bottom-0 z-30 flex gap-2 border-t border-line bg-surface/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur lg:hidden">
        <Button variant="outline" className="flex-1" onClick={() => setPaletteOpen(true)} icon={<Grid3X3 className="size-4" />}>
          {summary.answered}/{total} answered
        </Button>
        <Button className="flex-1" onClick={() => setConfirmOpen(true)} disabled={!active} icon={<Send className="size-4" />}>
          Submit
        </Button>
      </div>

      <Modal open={paletteOpen} onClose={() => setPaletteOpen(false)} title="Questions" className="max-w-md">
        {palette}
      </Modal>

      <ConfirmDialog
        open={confirmOpen && active}
        title="Submit your test?"
        description="You won't be able to change your answers after submitting."
        confirmLabel="Submit test"
        cancelLabel="Keep working"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          void exam.submit("manual");
        }}
      >
        <dl className="grid grid-cols-3 gap-2 text-center">
          <SummaryStat label="Answered" value={summary.answered} tone="text-emerald-600 dark:text-emerald-400" />
          <SummaryStat label="Unanswered" value={summary.unanswered} tone="text-rose-600 dark:text-rose-400" />
          <SummaryStat label="Marked" value={summary.marked} tone="text-violet-600 dark:text-violet-400" />
        </dl>
        {(summary.unanswered > 0 || summary.marked > 0) && (
          <Alert tone="warning" className="mt-4">
            {summary.unanswered > 0 && <>You have {pluralize(summary.unanswered, "unanswered question")}. </>}
            {summary.marked > 0 && <>{pluralize(summary.marked, "question")} marked for review.</>}
          </Alert>
        )}
      </ConfirmDialog>

      <Modal
        open={exam.phase === "submitting"}
        onClose={() => undefined}
        dismissible={false}
        title={exam.submitReason === "timeout" ? "Time's up!" : "Submitting your test"}
        description={exam.submitReason === "timeout" ? "Your answers are being submitted automatically." : "Grading your answers…"}
      >
        <div className="flex items-center gap-3 text-sm text-muted">
          <Loader2 className="size-5 animate-spin text-brand-500" />
          {exam.submitError ?? "Please keep this page open."}
        </div>
      </Modal>

      <ConfirmDialog
        open={blocker.state === "blocked" && (active || exam.phase === "submitting")}
        title="Leave the exam?"
        description="Your answers are saved, but the timer keeps running while you're away. You can resume from the Tests page."
        confirmLabel="Leave"
        cancelLabel="Stay"
        tone="danger"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      />
    </div>
  );
}

function SyncIndicator({ state, pending, onRetry }: { state: SyncState; pending: number; onRetry: () => void }) {
  if (state === "offline")
    return (
      <button onClick={onRetry} className="flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400" aria-live="polite">
        <CloudOff className="size-3.5" /> Offline — {pluralize(pending, "change")} waiting · retry
      </button>
    );
  if (state === "saving" || pending > 0)
    return (
      <p className="flex items-center gap-1 text-xs text-muted" aria-live="polite">
        <Loader2 className="size-3.5 animate-spin" /> Saving…
      </p>
    );
  return (
    <p className="flex items-center gap-1 text-xs text-muted" aria-live="polite">
      <Check className="size-3.5 text-emerald-500" /> All answers saved
    </p>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <dd className={clsx("text-2xl font-bold tabular-nums", tone)}>{value}</dd>
      <dt className="text-xs text-muted">{label}</dt>
    </div>
  );
}
