import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Eye, Plus, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { QuestionEditor } from "../components/tests/QuestionEditor";
import { TestSettingsForm } from "../components/tests/TestSettingsForm";
import { Button, ButtonLink } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/Modal";
import { Alert, Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/primitives";
import { useLeaveGuard } from "../hooks/useLeaveGuard";
import { api, ApiError } from "../lib/api";
import { pluralize } from "../lib/format";
import { draftFingerprint, draftFromTest, emptyDraft, newKey, newQuestion, toPayload, validateDraft, type DraftTest } from "../lib/testDraft";
import type { TestDetail, TestStatus } from "../lib/types";

interface LocationState {
  warnings?: string[];
}

export function EditTestPage() {
  const { testId } = useParams();
  const id = testId ? Number(testId) : null;
  const query = useQuery({
    queryKey: ["test", id],
    queryFn: () => api.getTest(id!),
    enabled: id !== null && Number.isFinite(id),
  });

  if (id !== null && !Number.isFinite(id)) return <ErrorState error={new Error("Invalid test id.")} />;
  if (id === null) return <TestEditor key="new" initial={null} />;
  if (query.isPending) return <Spinner label="Loading test…" />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  return <TestEditor key={query.data.id} initial={query.data} />;
}

function TestEditor({ initial }: { initial: TestDetail | null }) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const warnings = (location.state as LocationState | null)?.warnings ?? [];

  const [draft, setDraft] = useState<DraftTest>(() => (initial ? draftFromTest(initial) : emptyDraft()));
  const [saved, setSaved] = useState<TestDetail | null>(initial);
  const [baseline, setBaseline] = useState(() => draftFingerprint(draft));
  const [showErrors, setShowErrors] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const lastAdded = useRef<string | null>(null);

  const status: TestStatus = saved?.status ?? "draft";
  const dirty = draftFingerprint(draft) !== baseline;

  const errorsAsDraft = useMemo(() => validateDraft(draft, { publishing: false }), [draft]);
  const errorsAsPublished = useMemo(() => validateDraft(draft, { publishing: true }), [draft]);

  const mutation = useMutation({
    mutationFn: (nextStatus: TestStatus) => {
      const payload = toPayload(draft, nextStatus);
      return saved ? api.updateTest(saved.id, payload) : api.createTest(payload);
    },
    onSuccess: (test, nextStatus) => {
      const wasNew = !saved;
      setSaved(test);
      // Re-key from the server so new questions receive their ids.
      const next = draftFromTest(test);
      setDraft(next);
      setBaseline(draftFingerprint(next));
      setShowErrors(false);
      queryClient.setQueryData(["test", test.id], test);
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      toast.success(
        nextStatus === "published" ? (status === "published" ? "Changes saved" : "Test published — ready to take!") : "Draft saved",
      );
      if (wasNew) navigate(`/tests/${test.id}/edit`, { replace: true });
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : "Could not save the test.");
    },
  });

  const blocker = useLeaveGuard(dirty && !mutation.isPending);

  useEffect(() => {
    if (lastAdded.current) {
      document.getElementById(`question-${lastAdded.current}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      lastAdded.current = null;
    }
  }, [draft.questions.length]);

  const save = (nextStatus: TestStatus) => {
    const errors = nextStatus === "published" ? errorsAsPublished : errorsAsDraft;
    if (errors.count > 0) {
      setShowErrors(true);
      const firstQuestionKey = draft.questions.find((q) => errors.questions[q.key])?.key;
      if (Object.keys(errors.fields).length) window.scrollTo({ top: 0, behavior: "smooth" });
      else if (firstQuestionKey)
        document.getElementById(`question-${firstQuestionKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      toast.error(`Please fix ${pluralize(errors.count, "problem")} before saving.`);
      return;
    }
    mutation.mutate(nextStatus);
  };

  const updateQuestion = (index: number, patch: DraftTest["questions"][number]) =>
    setDraft((d) => ({ ...d, questions: d.questions.map((q, i) => (i === index ? patch : q)) }));

  const moveQuestion = (index: number, direction: -1 | 1) =>
    setDraft((d) => {
      const questions = [...d.questions];
      const target = index + direction;
      if (target < 0 || target >= questions.length) return d;
      [questions[index], questions[target]] = [questions[target], questions[index]];
      return { ...d, questions };
    });

  const addQuestion = () => {
    const question = newQuestion(draft.topic);
    lastAdded.current = question.key;
    setDraft((d) => ({ ...d, questions: [...d.questions, question] }));
  };

  const duplicateQuestion = (index: number) =>
    setDraft((d) => {
      const source = d.questions[index];
      const copy = { ...source, id: undefined, key: newKey(), options: [...source.options] };
      lastAdded.current = copy.key;
      const questions = [...d.questions];
      questions.splice(index + 1, 0, copy);
      return { ...d, questions };
    });

  const removeQuestion = (key: string) => setDraft((d) => ({ ...d, questions: d.questions.filter((q) => q.key !== key) }));

  const activeErrors = status === "published" ? errorsAsPublished : errorsAsDraft;
  const visibleCount = showErrors ? activeErrors.count : 0;

  return (
    <div className="pb-28">
      <PageHeader
        eyebrow={
          <button onClick={() => navigate(saved ? `/tests/${saved.id}` : "/tests")} className="inline-flex items-center gap-1 hover:text-fg">
            <ArrowLeft className="size-4" /> {saved ? "Back to test" : "Back to tests"}
          </button>
        }
        title={saved ? "Edit test" : "Create test manually"}
        description={saved ? "Review every question, then publish when it's ready." : "Write your own questions and publish when you're done."}
        actions={
          saved && (
            <>
              <Badge tone={status === "published" ? "success" : "warning"}>{status === "published" ? "Published" : "Draft"}</Badge>
              {saved.source === "ai" && (
                <Badge tone="brand">
                  <Sparkles className="size-3" /> AI generated
                </Badge>
              )}
            </>
          )
        }
      />

      {(warnings.length > 0 || saved?.generation_notes) && (
        <div className="mb-6 space-y-3">
          {warnings.length > 0 && (
            <Alert tone="warning" icon={<TriangleAlert className="size-4" />} title="Generation notes">
              <ul className="list-disc pl-4">
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Alert>
          )}
          {saved?.generation_notes && (
            <Alert tone="brand" icon={<Sparkles className="size-4" />} title="AI quality review">
              {saved.generation_notes}
            </Alert>
          )}
        </div>
      )}
      {saved?.source === "ai" && status === "draft" && (
        <Alert tone="info" className="mb-6">
          AI can make mistakes. Check each question and its marked answer before publishing.
        </Alert>
      )}

      <div className="space-y-6">
        <TestSettingsForm draft={draft} errors={activeErrors.fields} showErrors={showErrors} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))} />

        <section aria-labelledby="questions-heading" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 id="questions-heading" className="text-lg font-semibold">
              Questions <span className="text-muted">({draft.questions.length})</span>
            </h2>
            <Button variant="outline" size="sm" icon={<Plus className="size-4" />} onClick={addQuestion}>
              Add question
            </Button>
          </div>
          {showErrors && activeErrors.fields.questions && <Alert tone="danger">{activeErrors.fields.questions}</Alert>}
          {draft.questions.length === 0 ? (
            <Card>
              <EmptyState title="No questions yet" description="Add your first question to get started." action={<Button icon={<Plus className="size-4" />} onClick={addQuestion}>Add question</Button>} />
            </Card>
          ) : (
            draft.questions.map((question, index) => (
              <QuestionEditor
                key={question.key}
                index={index}
                total={draft.questions.length}
                question={question}
                errors={activeErrors.questions[question.key]}
                showErrors={showErrors}
                onChange={(q) => updateQuestion(index, q)}
                onMove={(direction) => moveQuestion(index, direction)}
                onDuplicate={() => duplicateQuestion(index)}
                onRemove={() => (question.text || question.options.some(Boolean) ? setPendingDelete(question.key) : removeQuestion(question.key))}
              />
            ))
          )}
          {draft.questions.length > 0 && (
            <Button variant="outline" className="w-full border-dashed" icon={<Plus className="size-4" />} onClick={addQuestion}>
              Add another question
            </Button>
          )}
        </section>
      </div>

      {/* Sticky action bar */}
      <div className="fixed inset-x-0 bottom-16 z-20 border-t border-line bg-surface/95 backdrop-blur md:bottom-0">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-6">
          <p className="text-sm text-muted" aria-live="polite">
            {visibleCount > 0 ? (
              <span className="font-medium text-rose-600 dark:text-rose-400">{pluralize(visibleCount, "problem")} to fix</span>
            ) : dirty ? (
              "Unsaved changes"
            ) : saved ? (
              "All changes saved"
            ) : (
              "Not saved yet"
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            {saved && status === "published" && !dirty && (
              <ButtonLink to={`/tests/${saved.id}`} variant="outline" size="md" icon={<Eye className="size-4" />}>
                View
              </ButtonLink>
            )}
            {status === "published" ? (
              <>
                <Button variant="outline" onClick={() => save("draft")} disabled={mutation.isPending}>
                  Unpublish
                </Button>
                <Button onClick={() => save("published")} loading={mutation.isPending} disabled={!dirty}>
                  Save changes
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => save("draft")} loading={mutation.isPending && mutation.variables === "draft"} disabled={mutation.isPending}>
                  Save draft
                </Button>
                <Button onClick={() => save("published")} loading={mutation.isPending && mutation.variables === "published"} disabled={mutation.isPending}>
                  Publish
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this question?"
        description="This only takes effect when you save the test."
        confirmLabel="Delete"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) removeQuestion(pendingDelete);
          setPendingDelete(null);
        }}
      />
      <ConfirmDialog
        open={blocker.state === "blocked" && dirty}
        title="Discard unsaved changes?"
        description="You have edits that haven't been saved yet."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        tone="danger"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      />
    </div>
  );
}
