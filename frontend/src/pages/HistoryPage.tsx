import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History as HistoryIcon, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button, ButtonLink } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/Modal";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Segmented, Skeleton } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import { formatDate, formatDuration, formatMarks, formatPercent, scoreTone } from "../lib/format";
import type { AttemptStatus, AttemptSummary } from "../lib/types";

type Filter = "" | AttemptStatus;

export function HistoryPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Filter>("");
  const [toDelete, setToDelete] = useState<AttemptSummary | null>(null);
  const attempts = useQuery({
    queryKey: ["attempts", { status }],
    queryFn: () => api.listAttempts({ status, limit: 200 }),
  });

  const remove = useMutation({
    mutationFn: (attempt: AttemptSummary) => api.deleteAttempt(attempt.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attempts"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      toast.success("Attempt deleted");
      setToDelete(null);
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not delete the attempt."),
  });

  return (
    <>
      <PageHeader
        title="History"
        description="Every attempt you've made, with scores and time spent."
        actions={
          <Segmented<Filter>
            ariaLabel="Filter attempts"
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: "All" },
              { value: "submitted", label: "Completed" },
              { value: "in_progress", label: "In progress" },
            ]}
          />
        }
      />

      {attempts.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 rounded-2xl" />
          ))}
        </div>
      ) : attempts.isError ? (
        <Card>
          <ErrorState error={attempts.error} onRetry={() => attempts.refetch()} title="Couldn't load history" />
        </Card>
      ) : attempts.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<HistoryIcon className="size-6" />}
            title={status ? "Nothing here" : "No attempts yet"}
            description={status ? "No attempts match this filter." : "Take a test and your results will appear here."}
            action={!status && <ButtonLink to="/tests">Browse tests</ButtonLink>}
          />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          {/* Desktop table */}
          <table className="hidden w-full text-sm md:table">
            <thead className="bg-surface-2 text-left text-xs tracking-wide text-muted uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Test</th>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 text-right font-medium">Score</th>
                <th className="px-4 py-3 text-center font-medium">✓ / ✗ / –</th>
                <th className="px-4 py-3 text-right font-medium">Time</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {attempts.data.map((a) => (
                <tr key={a.id} className="hover:bg-surface-2/60" data-testid="history-row">
                  <td className="max-w-xs px-4 py-3">
                    <Link to={a.status === "submitted" ? `/attempts/${a.id}/result` : `/attempts/${a.id}`} className="font-medium hover:text-brand-600 dark:hover:text-brand-400">
                      {a.test_title}
                    </Link>
                    <div className="truncate text-xs text-muted">{[a.subject, a.topic].filter(Boolean).join(" · ") || "—"}</div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted">{formatDate(a.started_at, true)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {a.status === "submitted" ? (
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-muted tabular-nums">
                          {formatMarks(a.score)}/{formatMarks(a.max_score)}
                        </span>
                        <Badge tone={scoreTone(a.percentage)}>{formatPercent(a.percentage)}</Badge>
                      </div>
                    ) : (
                      <Badge tone="info">In progress</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center text-muted tabular-nums">
                    {a.status === "submitted" ? `${a.correct_count} / ${a.incorrect_count} / ${a.unanswered_count}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap text-muted tabular-nums">
                    {formatDuration(a.time_spent_seconds)}
                    {a.submit_reason === "timeout" && <span className="ml-1 text-xs text-amber-600">(timed out)</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <AttemptActions attempt={a} onDelete={setToDelete} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Mobile list */}
          <ul className="divide-y divide-line md:hidden">
            {attempts.data.map((a) => (
              <li key={a.id} className="flex items-center gap-3 p-4" data-testid="history-row">
                <Link to={a.status === "submitted" ? `/attempts/${a.id}/result` : `/attempts/${a.id}`} className="min-w-0 flex-1">
                  <p className="truncate font-medium">{a.test_title}</p>
                  <p className="text-xs text-muted">
                    {formatDate(a.started_at, true)}
                    {a.status === "submitted" && ` · ${a.correct_count}/${a.question_count} correct · ${formatDuration(a.time_spent_seconds)}`}
                  </p>
                </Link>
                {a.status === "submitted" ? <Badge tone={scoreTone(a.percentage)}>{formatPercent(a.percentage)}</Badge> : <Badge tone="info">In progress</Badge>}
                <AttemptActions attempt={a} onDelete={setToDelete} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="Delete this attempt?"
        description="Its result will be removed from your history and analytics. This can't be undone."
        confirmLabel="Delete"
        tone="danger"
        loading={remove.isPending}
        onCancel={() => setToDelete(null)}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
      />
    </>
  );
}

function AttemptActions({ attempt, onDelete }: { attempt: AttemptSummary; onDelete: (a: AttemptSummary) => void }) {
  return (
    <div className="flex justify-end gap-1">
      {attempt.status === "in_progress" && (
        <ButtonLink to={`/attempts/${attempt.id}`} size="sm" variant="success" icon={<Play className="size-3.5" />}>
          Resume
        </ButtonLink>
      )}
      <Button variant="ghost" size="icon" aria-label={`Delete attempt of ${attempt.test_title}`} onClick={() => onDelete(attempt)}>
        <Trash2 className="size-4" />
      </Button>
    </div>
  );
}
