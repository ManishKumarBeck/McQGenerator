import { useQuery } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, Clock, Gauge, Target, Trophy } from "lucide-react";
import { ScoreTrendChart, TopicAccuracyChart } from "../components/charts/Charts";
import { ButtonLink } from "../components/ui/Button";
import { Card, EmptyState, ErrorState, PageHeader, ProgressBar, Skeleton, StatCard } from "../components/ui/primitives";
import { api } from "../lib/api";
import { formatDuration, formatPercent, scoreTone } from "../lib/format";

export function AnalyticsPage() {
  const analytics = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });

  if (analytics.isPending)
    return (
      <>
        <PageHeader title="Analytics" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      </>
    );
  if (analytics.isError)
    return (
      <Card>
        <ErrorState error={analytics.error} onRetry={() => analytics.refetch()} title="Couldn't load analytics" />
      </Card>
    );

  const { summary, topics, subjects, trend } = analytics.data;

  if (summary.total_attempts === 0)
    return (
      <>
        <PageHeader title="Analytics" description="Track accuracy, scores and weak topics over time." />
        <Card>
          <EmptyState
            icon={<BarChart3 className="size-6" />}
            title="No data yet"
            description="Complete a test to see your performance statistics here."
            action={<ButtonLink to="/tests">Take a test</ButtonLink>}
          />
        </Card>
      </>
    );

  const weakest = [...topics].filter((t) => t.accuracy !== null && t.correct + t.incorrect >= 1).sort((a, b) => (a.accuracy ?? 0) - (b.accuracy ?? 0)).slice(0, 3);

  return (
    <>
      <PageHeader title="Analytics" description="Track accuracy, scores and weak topics over time." />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
        <StatCard label="Tests completed" value={summary.total_attempts} hint={summary.tests_taken === 1 ? "from 1 test" : `across ${summary.tests_taken} tests`} icon={<CheckCircle2 className="size-5" />} tone="success" />
        <StatCard label="Average score" value={formatPercent(summary.average_percentage)} icon={<Gauge className="size-5" />} tone="brand" />
        <StatCard label="Best score" value={formatPercent(summary.best_percentage)} icon={<Trophy className="size-5" />} tone="warning" />
        <StatCard
          label="Accuracy"
          value={formatPercent(summary.accuracy)}
          hint={`${summary.total_correct} correct · ${summary.total_incorrect} wrong · ${summary.total_unanswered} skipped`}
          icon={<Target className="size-5" />}
          tone="info"
        />
        <StatCard label="Time practising" value={formatDuration(summary.total_time_seconds)} icon={<Clock className="size-5" />} tone="neutral" />
        <StatCard label="Avg time / question" value={formatDuration(summary.average_time_per_question_seconds)} icon={<Clock className="size-5" />} tone="neutral" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <h2 className="text-base font-semibold">Score trend</h2>
          <p className="mb-4 text-xs text-muted">Last {trend.length} completed attempts, oldest first</p>
          <ScoreTrendChart data={trend} />
        </Card>
        <Card className="p-5 sm:p-6">
          <h2 className="text-base font-semibold">Accuracy by topic</h2>
          <p className="mb-4 text-xs text-muted">Share of attempted questions answered correctly</p>
          {topics.length ? <TopicAccuracyChart topics={topics} /> : <p className="text-sm text-muted">No topic data yet.</p>}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 text-base font-semibold">Focus areas</h2>
          {weakest.length === 0 ? (
            <p className="text-sm text-muted">Answer some questions to see which topics need work.</p>
          ) : (
            <ul className="space-y-4">
              {weakest.map((t) => (
                <li key={t.topic}>
                  <div className="mb-1.5 flex justify-between text-sm">
                    <span className="font-medium">{t.topic}</span>
                    <span className="text-muted tabular-nums">{formatPercent(t.accuracy, 0)}</span>
                  </div>
                  <ProgressBar value={t.accuracy ?? 0} tone={scoreTone(t.accuracy) === "neutral" ? "neutral" : scoreTone(t.accuracy)} label={`${t.topic} accuracy`} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 text-base font-semibold">By subject</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="pb-2 font-medium">Subject</th>
                <th className="pb-2 text-right font-medium">Attempts</th>
                <th className="pb-2 text-right font-medium">Avg score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {subjects.map((s) => (
                <tr key={s.subject}>
                  <td className="py-2.5">{s.subject}</td>
                  <td className="py-2.5 text-right tabular-nums">{s.attempts}</td>
                  <td className="py-2.5 text-right tabular-nums">{formatPercent(s.average_percentage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
