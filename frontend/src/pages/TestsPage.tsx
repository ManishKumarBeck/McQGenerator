import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, PenLine, Plus, Search, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { PdfExportDialog } from "../components/tests/PdfExportDialog";
import { TestCard } from "../components/tests/TestCard";
import { ButtonLink } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/Modal";
import { Card, EmptyState, ErrorState, Input, PageHeader, Segmented, Skeleton } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import type { TestStatus, TestSummary } from "../lib/types";

type Filter = "" | TestStatus;

export function TestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as Filter;
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(search);
  const [toDelete, setToDelete] = useState<TestSummary | null>(null);
  const [toDownload, setToDownload] = useState<TestSummary | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const tests = useQuery({
    queryKey: ["tests", { search: debounced, status }],
    queryFn: () => api.listTests({ search: debounced, status }),
    placeholderData: keepPreviousData,
  });

  const duplicate = useMutation({
    mutationFn: (test: TestSummary) => api.duplicateTest(test.id),
    onSuccess: (copy) => {
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      toast.success("Test duplicated as a draft");
      navigate(`/tests/${copy.id}/edit`);
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not duplicate the test."),
  });

  const remove = useMutation({
    mutationFn: (test: TestSummary) => api.deleteTest(test.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success("Test deleted. Past results are kept in History.");
      setToDelete(null);
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not delete the test."),
  });

  const setStatus = (value: Filter) => {
    const next = new URLSearchParams(params);
    if (value) next.set("status", value);
    else next.delete("status");
    setParams(next, { replace: true });
  };

  const filtering = Boolean(debounced || status);

  return (
    <>
      <PageHeader
        title="Tests"
        description="Your question banks. Generate with AI or write your own."
        actions={
          <>
            <ButtonLink to="/tests/new/manual" variant="outline" icon={<PenLine className="size-4" />}>
              Write manually
            </ButtonLink>
            <ButtonLink to="/tests/new" icon={<Sparkles className="size-4" />}>
              Generate with AI
            </ButtonLink>
          </>
        }
      />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by title, subject or topic"
            aria-label="Search tests"
            className="pl-9"
          />
        </div>
        <Segmented<Filter>
          ariaLabel="Filter by status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "", label: "All" },
            { value: "published", label: "Published" },
            { value: "draft", label: "Drafts" },
          ]}
        />
      </div>

      {tests.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-60 rounded-2xl" />
          ))}
        </div>
      ) : tests.isError ? (
        <Card>
          <ErrorState error={tests.error} onRetry={() => tests.refetch()} title="Couldn't load tests" />
        </Card>
      ) : tests.data.length === 0 ? (
        <Card>
          {filtering ? (
            <EmptyState icon={<Search className="size-6" />} title="No matching tests" description="Try a different search or filter." />
          ) : (
            <EmptyState
              icon={<ListChecks className="size-6" />}
              title="No tests yet"
              description="Create your first test by generating questions with AI or writing them yourself."
              action={
                <ButtonLink to="/tests/new" icon={<Plus className="size-4" />}>
                  Create a test
                </ButtonLink>
              }
            />
          )}
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {tests.data.map((test) => (
            <TestCard key={test.id} test={test} onDuplicate={(t) => duplicate.mutate(t)} onDelete={setToDelete} onDownload={setToDownload} />
          ))}
        </div>
      )}

      {toDownload && <PdfExportDialog testId={toDownload.id} open onClose={() => setToDownload(null)} />}
      <ConfirmDialog
        open={toDelete !== null}
        title={`Delete “${toDelete?.title ?? ""}”?`}
        description="The test and its questions will be removed. Results of past attempts stay in your history."
        confirmLabel="Delete test"
        tone="danger"
        loading={remove.isPending}
        onCancel={() => setToDelete(null)}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
      />
    </>
  );
}
