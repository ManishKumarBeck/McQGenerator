import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock, FileQuestion, Flag, MinusCircle, Pencil, Play, RotateCcw, Timer } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Button, ButtonLink } from "../components/ui/Button";
import { Alert, Badge, Card, ErrorState, PageHeader, Spinner, difficultyTone } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import { formatDate, formatDuration, formatMarks, formatPercent, scoreTone } from "../lib/format";

export function TestDetailPage() {
  const { testId } = useParams();
  const id = Number(testId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const test = useQuery({ queryKey: ["test", id], queryFn: () => api.getTest(id), enabled: Number.isFinite(id) });
  const attempts = useQuery({
    queryKey: ["attempts", { test_id: id }],
    queryFn: () => api.listAttempts({ test_id: id, limit: 10 }),
    enabled: Number.isFinite(id),
  });

  const start = useMutation({
    mutationFn: () => api.startAttempt(id),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      queryClient.setQueryData(["attempt-session", session.id], session);
      navigate(`/attempts/${session.id}`);
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not start the test."),
  });

  if (!Number.isFinite(id)) return <ErrorState error={new Error("Invalid test id.")} />;
  if (test.isPending) return <Spinner label="Loading test…" />;
  if (test.isError) return <ErrorState error={test.error} onRetry={() => test.refetch()} />;

  const t = test.data;
  const inProgress = t.in_progress_attempt_id;
  const maxScore = t.question_count * t.marks_per_question;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow={
          <Link to="/tests" className="inline-flex items-center gap-1 hover:text-fg">
            <ArrowLeft className="size-4" /> All tests
          </Link>
        }
        title={t.title}
        description={[t.subject, t.topic, t.category].filter(Boolean).join(" · ") || undefined}
        actions={
          <ButtonLink to={`/tests/${t.id}/edit`} variant="outline" icon={<Pencil className="size-4" />}>
            Edit
          </ButtonLink>
        }
      />

      <Card className="p-5 sm:p-6">
        <div className="mb-5 flex flex-wrap gap-2">
          <Badge tone={t.status === "published" ? "success" : "warning"}>{t.status === "published" ? "Published" : "Draft"}</Badge>
          <Badge tone={difficultyTone(t.difficulty)} className="capitalize">
            {t.difficulty}
          </Badge>
        </div>

        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Info icon={<FileQuestion className="size-4" />} label="Questions" value={t.question_count} />
          <Info icon={<Clock className="size-4" />} label="Duration" value={`${t.duration_minutes} min`} />
          <Info icon={<CheckCircle2 className="size-4" />} label="Correct" value={`+${formatMarks(t.marks_per_question)}`} />
          <Info icon={<MinusCircle className="size-4" />} label="Wrong" value={t.negative_marks > 0 ? `−${formatMarks(t.negative_marks)}` : "0"} />
        </dl>

        {t.description && <p className="mt-6 text-sm leading-relaxed whitespace-pre-line text-muted">{t.description}</p>}

        <div className="mt-6 rounded-xl bg-surface-2 p-4 text-sm">
          <h2 className="mb-2 font-semibold">Before you start</h2>
          <ul className="space-y-1.5 text-muted">
            <li className="flex gap-2">
              <Timer className="mt-0.5 size-4 shrink-0" /> The timer starts immediately and keeps running even if you close the page.
            </li>
            <li className="flex gap-2">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> Answers save automatically — you can refresh or come back and resume.
            </li>
            <li className="flex gap-2">
              <Flag className="mt-0.5 size-4 shrink-0" /> Mark questions for review and revisit them from the question palette.
            </li>
            <li className="flex gap-2">
              <Clock className="mt-0.5 size-4 shrink-0" /> The test is submitted automatically when time runs out. Maximum score: {formatMarks(maxScore)}.
            </li>
          </ul>
        </div>

        {t.status !== "published" ? (
          <Alert tone="warning" className="mt-6">
            This test is a draft. <Link to={`/tests/${t.id}/edit`} className="font-semibold underline">Review and publish it</Link> to start an attempt.
          </Alert>
        ) : (
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
            {inProgress ? (
              <ButtonLink to={`/attempts/${inProgress}`} size="lg" variant="success" icon={<RotateCcw className="size-5" />}>
                Resume attempt
              </ButtonLink>
            ) : (
              <Button size="lg" onClick={() => start.mutate()} loading={start.isPending} icon={<Play className="size-5" />}>
                Start test
              </Button>
            )}
          </div>
        )}
      </Card>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold">Your attempts</h2>
        {attempts.isPending ? (
          <Spinner />
        ) : attempts.isError ? (
          <ErrorState error={attempts.error} onRetry={() => attempts.refetch()} />
        ) : attempts.data.length === 0 ? (
          <p className="text-sm text-muted">No attempts yet.</p>
        ) : (
          <Card className="divide-y divide-line">
            {attempts.data.map((a) => (
              <Link
                key={a.id}
                to={a.status === "submitted" ? `/attempts/${a.id}/result` : `/attempts/${a.id}`}
                className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-2"
              >
                <div>
                  <p className="text-sm font-medium">{formatDate(a.started_at, true)}</p>
                  <p className="text-xs text-muted">
                    {a.status === "submitted"
                      ? `${a.correct_count}/${a.question_count} correct · ${formatDuration(a.time_spent_seconds)}${a.submit_reason === "timeout" ? " · time ran out" : ""}`
                      : "In progress"}
                  </p>
                </div>
                {a.status === "submitted" ? (
                  <Badge tone={scoreTone(a.percentage)}>{formatPercent(a.percentage)}</Badge>
                ) : (
                  <Badge tone="info">Resume</Badge>
                )}
              </Link>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}

function Info({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-xs text-muted">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
