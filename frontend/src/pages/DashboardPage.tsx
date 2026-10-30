import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Gauge, KeyRound, PenLine, Play, Sparkles, Target, Trophy } from "lucide-react";
import { Link } from "react-router";
import { ButtonLink } from "../components/ui/Button";
import { Alert, Badge, Card, EmptyState, PageHeader, Skeleton, StatCard } from "../components/ui/primitives";
import { api } from "../lib/api";
import { formatPercent, formatRelative, pluralize, scoreTone } from "../lib/format";

export function DashboardPage() {
  const analytics = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });
  const tests = useQuery({ queryKey: ["tests", { search: "", status: "" }], queryFn: () => api.listTests() });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });

  const summary = analytics.data?.summary;
  const inProgress = tests.data?.filter((t) => t.in_progress_attempt_id) ?? [];
  const recentTests = tests.data?.slice(0, 4) ?? [];

  return (
    <>
      <PageHeader title="Welcome back" description="Create tests in seconds, practise under exam conditions and watch your scores improve." />

      {health.data && !health.data.ai_configured && (
        <Alert tone="warning" className="mb-6" icon={<KeyRound className="size-4" />} title="AI generation is not configured">
          Set <code className="font-mono">OPENAI_API_KEY</code> in <code className="font-mono">.env</code> and restart the backend to generate questions with AI.
        </Alert>
      )}
      {health.isError && (
        <Alert tone="danger" className="mb-6" title="Can't reach the backend">
          Start the API server (see README) and refresh this page.
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Link to="/tests/new" className="group">
          <Card className="h-full bg-gradient-to-br from-brand-600 to-violet-600 p-6 text-white transition-transform group-hover:-translate-y-0.5">
            <Sparkles className="mb-3 size-7" />
            <h2 className="text-lg font-semibold">Generate a test with AI</h2>
            <p className="mt-1 text-sm text-white/80">From a topic, pasted notes or a PDF. Review every question before publishing.</p>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium">
              Start generating <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </span>
          </Card>
        </Link>
        <Link to="/tests/new/manual" className="group">
          <Card className="h-full p-6 transition-transform group-hover:-translate-y-0.5">
            <PenLine className="mb-3 size-7 text-brand-600 dark:text-brand-400" />
            <h2 className="text-lg font-semibold">Write your own questions</h2>
            <p className="mt-1 text-sm text-muted">Build a test by hand with explanations, topics and custom marking.</p>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400">
              Open editor <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </span>
          </Card>
        </Link>
      </div>

      {inProgress.length > 0 && (
        <Card className="mt-6 border-emerald-300 p-4 dark:border-emerald-500/40">
          <h2 className="mb-3 text-sm font-semibold">Continue where you left off</h2>
          <ul className="space-y-2">
            {inProgress.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3">
                <span className="truncate text-sm">{t.title}</span>
                <ButtonLink to={`/attempts/${t.in_progress_attempt_id}`} size="sm" variant="success" icon={<Play className="size-3.5" />}>
                  Resume
                </ButtonLink>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {analytics.isPending ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)
        ) : (
          <>
            <StatCard label="Tests taken" value={summary?.total_attempts ?? 0} icon={<CheckCircle2 className="size-5" />} tone="success" />
            <StatCard label="Average score" value={formatPercent(summary?.average_percentage)} icon={<Gauge className="size-5" />} />
            <StatCard label="Best score" value={formatPercent(summary?.best_percentage)} icon={<Trophy className="size-5" />} tone="warning" />
            <StatCard label="Accuracy" value={formatPercent(summary?.accuracy)} icon={<Target className="size-5" />} tone="info" />
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Recent results</h2>
            <Link to="/history" className="text-sm text-brand-600 hover:underline dark:text-brand-400">
              View all
            </Link>
          </div>
          {analytics.data?.recent_attempts.length ? (
            <ul className="divide-y divide-line">
              {analytics.data.recent_attempts.map((a) => (
                <li key={a.id}>
                  <Link to={`/attempts/${a.id}/result`} className="flex items-center justify-between gap-3 py-2.5 hover:text-brand-600 dark:hover:text-brand-400">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{a.test_title}</p>
                      <p className="text-xs text-muted">{formatRelative(a.submitted_at)}</p>
                    </div>
                    <Badge tone={scoreTone(a.percentage)}>{formatPercent(a.percentage)}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState className="py-8" title="No results yet" description="Your completed tests will show up here." />
          )}
        </Card>
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Your tests</h2>
            <Link to="/tests" className="text-sm text-brand-600 hover:underline dark:text-brand-400">
              View all
            </Link>
          </div>
          {recentTests.length ? (
            <ul className="divide-y divide-line">
              {recentTests.map((t) => (
                <li key={t.id}>
                  <Link
                    to={t.status === "published" ? `/tests/${t.id}` : `/tests/${t.id}/edit`}
                    className="flex items-center justify-between gap-3 py-2.5 hover:text-brand-600 dark:hover:text-brand-400"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{t.title}</p>
                      <p className="text-xs text-muted">
                        {pluralize(t.question_count, "question")} · {t.duration_minutes} min
                      </p>
                    </div>
                    <Badge tone={t.status === "published" ? "success" : "warning"}>{t.status === "published" ? "Ready" : "Draft"}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState className="py-8" title="No tests yet" description="Generate or write your first test to get started." />
          )}
        </Card>
      </div>
    </>
  );
}
