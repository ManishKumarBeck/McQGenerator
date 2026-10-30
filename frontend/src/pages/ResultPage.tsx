import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Check, CheckCircle2, Circle, Clock, Flag, Lightbulb, RotateCcw, Target, Timer, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Button } from "../components/ui/Button";
import { Alert, Badge, Card, ErrorState, PageHeader, ProgressBar, ProgressRing, Segmented, Spinner, StatCard } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import { formatDate, formatDuration, formatMarks, formatPercent, OPTION_LABELS, scoreTone } from "../lib/format";
import type { AttemptResult, ResultQuestion } from "../lib/types";

type Filter = "all" | "correct" | "incorrect" | "unanswered" | "marked";

export function ResultPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const result = useQuery({ queryKey: ["result", attemptId], queryFn: () => api.getResult(attemptId), staleTime: Infinity });

  const retake = useMutation({
    mutationFn: (testId: number) => api.startAttempt(testId),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      navigate(`/attempts/${session.id}`);
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not start a new attempt."),
  });

  if (result.isPending) return <Spinner label="Loading results…" />;
  if (result.isError) {
    const inProgress = result.error instanceof ApiError && result.error.code === "attempt_in_progress";
    return (
      <Card>
        <ErrorState
          error={result.error}
          title={inProgress ? "This attempt is still in progress" : "Couldn't load results"}
          onRetry={inProgress ? () => navigate(`/attempts/${attemptId}`) : () => result.refetch()}
        />
      </Card>
    );
  }

  return <ResultView result={result.data} onRetake={(id) => retake.mutate(id)} retaking={retake.isPending} />;
}

function ResultView({ result, onRetake, retaking }: { result: AttemptResult; onRetake: (testId: number) => void; retaking: boolean }) {
  const [filter, setFilter] = useState<Filter>("all");
  const tone = scoreTone(result.percentage);
  const pct = result.percentage ?? 0;

  const filtered = useMemo(
    () =>
      result.questions.filter((q) => {
        if (filter === "correct") return q.is_correct === true;
        if (filter === "incorrect") return q.is_correct === false;
        if (filter === "unanswered") return q.is_correct === null;
        if (filter === "marked") return q.marked_for_review;
        return true;
      }),
    [filter, result.questions],
  );

  const headline = pct >= 90 ? "Outstanding!" : pct >= 75 ? "Great work!" : pct >= 50 ? "Good effort" : pct >= 0 ? "Keep practising" : "Tough one — review and retry";

  return (
    <div>
      <PageHeader
        eyebrow={
          <Link to="/history" className="inline-flex items-center gap-1 hover:text-fg">
            <ArrowLeft className="size-4" /> History
          </Link>
        }
        title={result.test_title}
        description={`Submitted ${formatDate(result.submitted_at, true)}`}
        actions={
          result.test_id !== null && (
            <Button variant="outline" onClick={() => onRetake(result.test_id!)} loading={retaking} icon={<RotateCcw className="size-4" />}>
              Retake test
            </Button>
          )
        }
      />

      {result.submit_reason === "timeout" && (
        <Alert tone="warning" className="mb-6" icon={<Clock className="size-4" />}>
          Time ran out, so this test was submitted automatically. Answers saved before the deadline were graded.
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card className="flex flex-col items-center p-6 text-center">
          <ProgressRing value={pct} size={168} stroke={14} tone={tone === "neutral" ? "brand" : tone}>
            <span className="text-4xl font-bold tabular-nums" data-testid="score-percentage">
              {formatPercent(result.percentage)}
            </span>
            <span className="text-xs text-muted">score</span>
          </ProgressRing>
          <p className="mt-4 text-lg font-semibold">{headline}</p>
          <p className="mt-1 text-2xl font-bold tabular-nums" data-testid="score-marks">
            {formatMarks(result.score)} <span className="text-base font-medium text-muted">/ {formatMarks(result.max_score)} marks</span>
          </p>
          <p className="mt-2 text-xs text-muted">
            +{formatMarks(result.marks_per_question)} per correct
            {result.negative_marks > 0 ? ` · −${formatMarks(result.negative_marks)} per wrong` : " · no negative marking"}
          </p>
        </Card>

        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">
          <StatCard label="Correct" value={result.correct_count} icon={<CheckCircle2 className="size-5" />} tone="success" hint={`of ${result.question_count} questions`} />
          <StatCard label="Incorrect" value={result.incorrect_count} icon={<XCircle className="size-5" />} tone="danger" hint={result.negative_marks_total > 0 ? `−${formatMarks(result.negative_marks_total)} marks` : "no penalty"} />
          <StatCard label="Unanswered" value={result.unanswered_count} icon={<Circle className="size-5" />} tone="neutral" />
          <StatCard label="Accuracy" value={formatPercent(result.accuracy)} icon={<Target className="size-5" />} tone="brand" hint="of attempted questions" />
          <StatCard label="Time taken" value={formatDuration(result.time_spent_seconds)} icon={<Clock className="size-5" />} tone="info" hint={`of ${formatDuration(result.duration_seconds)}`} />
          <StatCard
            label="Avg / question"
            value={formatDuration(result.question_count ? (result.time_spent_seconds ?? 0) / result.question_count : null)}
            icon={<Timer className="size-5" />}
            tone="warning"
          />
        </div>
      </div>

      {result.topic_breakdown.length > 1 && (
        <Card className="mt-6 p-5 sm:p-6">
          <h2 className="mb-4 text-base font-semibold">Performance by topic</h2>
          <ul className="space-y-4">
            {result.topic_breakdown.map((t) => (
              <li key={t.topic}>
                <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium">{t.topic}</span>
                  <span className="text-muted tabular-nums">
                    {t.correct}/{t.total} correct
                    {t.incorrect > 0 && ` · ${t.incorrect} wrong`}
                    {t.unanswered > 0 && ` · ${t.unanswered} skipped`}
                  </span>
                </div>
                <ProgressBar value={(t.correct / t.total) * 100} tone={scoreTone(t.accuracy) === "neutral" ? "neutral" : scoreTone(t.accuracy)} label={`${t.topic} score`} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      <section className="mt-8" aria-labelledby="review-heading">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 id="review-heading" className="text-lg font-semibold">
            Answer review
          </h2>
          <Segmented<Filter>
            ariaLabel="Filter questions"
            className="flex w-full overflow-x-auto sm:w-auto"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: `All ${result.question_count}` },
              { value: "correct", label: `Correct ${result.correct_count}` },
              { value: "incorrect", label: `Wrong ${result.incorrect_count}` },
              { value: "unanswered", label: `Skipped ${result.unanswered_count}` },
              { value: "marked", label: "Marked" },
            ]}
          />
        </div>
        {filtered.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted">No questions in this category.</Card>
        ) : (
          <div className="space-y-4">
            {filtered.map((q) => (
              <ReviewCard key={q.position} question={q} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ReviewCard({ question: q }: { question: ResultQuestion }) {
  const status = q.is_correct === true ? "correct" : q.is_correct === false ? "incorrect" : "unanswered";
  return (
    <Card className="p-5 sm:p-6" data-testid="review-card" data-status={status}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-muted">Q{q.position + 1}</span>
        {status === "correct" && <Badge tone="success">Correct · +{formatMarks(q.marks_awarded)}</Badge>}
        {status === "incorrect" && <Badge tone="danger">Incorrect · {formatMarks(q.marks_awarded)}</Badge>}
        {status === "unanswered" && <Badge>Not answered · 0</Badge>}
        {q.topic && <Badge>{q.topic}</Badge>}
        {q.marked_for_review && (
          <Badge tone="brand">
            <Flag className="size-3" /> Marked
          </Badge>
        )}
        {q.time_spent_seconds > 0 && <span className="ml-auto text-xs text-muted">{formatDuration(q.time_spent_seconds)}</span>}
      </div>
      <p className="font-medium whitespace-pre-line">{q.text}</p>
      <ul className="mt-4 space-y-2">
        {q.options.map((option, index) => {
          const isCorrect = index === q.correct_option;
          const isChosen = index === q.selected_option;
          return (
            <li
              key={index}
              className={clsx(
                "flex items-start gap-3 rounded-xl border p-3 text-sm",
                isCorrect
                  ? "border-emerald-300 bg-emerald-50 dark:border-emerald-500/40 dark:bg-emerald-500/10"
                  : isChosen
                    ? "border-rose-300 bg-rose-50 dark:border-rose-500/40 dark:bg-rose-500/10"
                    : "border-line",
              )}
            >
              <span
                className={clsx(
                  "flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold",
                  isCorrect ? "bg-emerald-500 text-white" : isChosen ? "bg-rose-500 text-white" : "bg-surface-2 text-muted",
                )}
              >
                {isCorrect ? <Check className="size-3.5" /> : isChosen ? <XCircle className="size-3.5" /> : OPTION_LABELS[index]}
              </span>
              <span className="flex-1 pt-0.5">{option}</span>
              {isChosen && <span className="shrink-0 pt-0.5 text-xs font-medium text-muted">Your answer</span>}
              {isCorrect && !isChosen && <span className="shrink-0 pt-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">Correct answer</span>}
            </li>
          );
        })}
      </ul>
      {q.explanation && (
        <div className="mt-4 flex gap-2 rounded-xl bg-surface-2 p-3 text-sm">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-amber-500" />
          <p className="leading-relaxed text-muted">{q.explanation}</p>
        </div>
      )}
    </Card>
  );
}
