import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileText, KeyRound, PenLine, Sparkles, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { DIFFICULTY_OPTIONS } from "../components/tests/TestSettingsForm";
import { Button, ButtonLink } from "../components/ui/Button";
import { Alert, Card, Field, Input, PageHeader, Segmented, Switch, Textarea } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import type { Difficulty } from "../lib/types";

const MAX_FILE_MB = 5;
const ACCEPTED = [".pdf", ".txt", ".md"];
const MAX_QUESTIONS = 30;

type SourceMode = "topic" | "text" | "file";

const LOADING_MESSAGES = [
  "Reading your material…",
  "Drafting questions…",
  "Writing plausible distractors…",
  "Adding explanations…",
  "Checking answers…",
];

export function CreateTestPage() {
  const id = useId();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });

  const [subject, setSubject] = useState("");
  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState("");
  const [title, setTitle] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [count, setCount] = useState<number | "">(10);
  const [mode, setMode] = useState<SourceMode>("topic");
  const [sourceText, setSourceText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [instructions, setInstructions] = useState("");
  const [duration, setDuration] = useState<number | "">("");
  const [marks, setMarks] = useState<number | "">(1);
  const [negative, setNegative] = useState<number | "">(0);
  const [review, setReview] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dragging, setDragging] = useState(false);
  const [messageIndex, setMessageIndex] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const generate = useMutation({
    mutationFn: () => {
      abortRef.current = new AbortController();
      return api.generateTest(
        {
          title: title.trim(),
          subject: subject.trim(),
          topic: topic.trim(),
          category: category.trim(),
          difficulty,
          question_count: Number(count),
          source_text: mode === "text" ? sourceText.trim() : "",
          instructions: instructions.trim(),
          duration_minutes: duration === "" ? null : Number(duration),
          marks_per_question: Number(marks),
          negative_marks: Number(negative),
          quality_review: review,
          file: mode === "file" ? file : null,
        },
        abortRef.current.signal,
      );
    },
    onSuccess: ({ test, warnings }) => {
      queryClient.invalidateQueries({ queryKey: ["tests"] });
      queryClient.setQueryData(["test", test.id], test);
      toast.success(`Generated ${test.question_count} questions. Review them before publishing.`);
      navigate(`/tests/${test.id}/edit`, { state: { warnings } });
    },
    onError: (error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        toast.info("Stopped waiting. If the server had already finished, the draft will appear under Tests.");
        return;
      }
      toast.error(error instanceof ApiError ? error.message : "Generation failed.");
    },
  });

  useEffect(() => {
    if (!generate.isPending) return;
    const timer = window.setInterval(() => setMessageIndex((i) => Math.min(i + 1, LOADING_MESSAGES.length - 1)), 6000);
    return () => window.clearInterval(timer);
  }, [generate.isPending]);

  const pickFile = (candidate: File | undefined | null) => {
    if (!candidate) return;
    const lower = candidate.name.toLowerCase();
    if (!ACCEPTED.some((ext) => lower.endsWith(ext))) {
      setErrors((e) => ({ ...e, file: "Upload a PDF, TXT or MD file." }));
      return;
    }
    if (candidate.size > MAX_FILE_MB * 1024 * 1024) {
      setErrors((e) => ({ ...e, file: `That file is larger than ${MAX_FILE_MB} MB.` }));
      return;
    }
    if (candidate.size === 0) {
      setErrors((e) => ({ ...e, file: "That file is empty." }));
      return;
    }
    setErrors(({ file: _ignored, ...rest }) => rest);
    setFile(candidate);
  };

  const validate = () => {
    const next: Record<string, string> = {};
    if (count === "" || !Number.isInteger(count) || count < 1 || count > MAX_QUESTIONS)
      next.count = `Choose between 1 and ${MAX_QUESTIONS} questions.`;
    if (mode === "topic" && !subject.trim() && !topic.trim()) next.topic = "Enter a subject or topic to generate from.";
    if (mode === "text" && sourceText.trim().length < 50) next.sourceText = "Paste at least a paragraph (50+ characters) of material.";
    if (mode === "file" && !file) next.file = "Choose a file to upload.";
    if (duration !== "" && (!Number.isInteger(duration) || duration < 1 || duration > 600)) next.duration = "1–600 minutes.";
    if (marks === "" || marks <= 0 || marks > 100) next.marks = "Must be greater than 0.";
    if (negative === "" || negative < 0) next.negative = "Can't be negative.";
    else if (marks !== "" && negative > marks) next.negative = "Can't exceed marks per question.";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!validate()) return;
    setMessageIndex(0);
    generate.mutate();
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    pickFile(event.dataTransfer.files?.[0]);
  };

  const aiConfigured = health.data?.ai_configured ?? true;
  const busy = generate.isPending;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Create a test"
        description="Generate questions with AI from a topic, your notes or a document — then review and edit them."
        actions={
          <ButtonLink to="/tests/new/manual" variant="outline" icon={<PenLine className="size-4" />}>
            Write manually
          </ButtonLink>
        }
      />

      {!aiConfigured && (
        <Alert tone="warning" className="mb-6" icon={<KeyRound className="size-4" />} title="AI generation isn't configured">
          Add <code className="font-mono">OPENAI_API_KEY</code> to the <code className="font-mono">.env</code> file and restart the backend. You can still
          create tests manually.
        </Alert>
      )}

      <form onSubmit={onSubmit} noValidate>
        <fieldset disabled={busy} className="space-y-6">
          <Card className="p-4 sm:p-6">
            <h2 className="mb-1 text-base font-semibold">What should the questions cover?</h2>
            <p className="mb-4 text-sm text-muted">Pick a source. Uploaded and pasted material keeps questions grounded in your content.</p>
            <Segmented<SourceMode>
              ariaLabel="Question source"
              className="mb-5 flex w-full"
              value={mode}
              onChange={setMode}
              options={[
                { value: "topic", label: "Topic" },
                { value: "text", label: "Paste text" },
                { value: "file", label: "Upload file" },
              ]}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field htmlFor={`${id}-subject`} label="Subject">
                <Input id={`${id}-subject`} value={subject} maxLength={100} placeholder="e.g. Biology" onChange={(e) => setSubject(e.target.value)} />
              </Field>
              <Field htmlFor={`${id}-topic`} label="Topic" error={errors.topic}>
                <Input id={`${id}-topic`} value={topic} maxLength={150} invalid={!!errors.topic} placeholder="e.g. Cell division" onChange={(e) => setTopic(e.target.value)} />
              </Field>
            </div>

            {mode === "text" && (
              <Field htmlFor={`${id}-source`} label="Source material" className="mt-4" error={errors.sourceText} hint={`${sourceText.length.toLocaleString()} characters`}>
                <Textarea
                  id={`${id}-source`}
                  rows={8}
                  value={sourceText}
                  invalid={!!errors.sourceText}
                  placeholder="Paste lecture notes, an article or a textbook section…"
                  onChange={(e) => setSourceText(e.target.value)}
                />
              </Field>
            )}

            {mode === "file" && (
              <div className="mt-4">
                {file ? (
                  <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-2 p-3">
                    <FileText className="size-8 shrink-0 text-brand-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{file.name}</p>
                      <p className="text-xs text-muted">{(file.size / 1024).toFixed(0)} KB</p>
                    </div>
                    <Button variant="ghost" size="icon" aria-label="Remove file" onClick={() => setFile(null)}>
                      <X className="size-4" />
                    </Button>
                  </div>
                ) : (
                  <label
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    className={clsx(
                      "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
                      dragging ? "border-brand-500 bg-brand-50 dark:bg-brand-500/10" : errors.file ? "border-rose-400" : "border-line hover:border-brand-400",
                    )}
                  >
                    <Upload className="mb-2 size-6 text-muted" />
                    <span className="text-sm font-medium">Drop a file here or click to browse</span>
                    <span className="mt-1 text-xs text-muted">PDF, TXT or MD · up to {MAX_FILE_MB} MB · text-based PDFs only</span>
                    <input
                      type="file"
                      accept={ACCEPTED.join(",")}
                      className="sr-only"
                      data-testid="file-input"
                      onChange={(e) => {
                        pickFile(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
                {errors.file && <p className="mt-1.5 text-xs font-medium text-rose-600 dark:text-rose-400">{errors.file}</p>}
              </div>
            )}
          </Card>

          <Card className="p-4 sm:p-6">
            <h2 className="mb-4 text-base font-semibold">Question settings</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Difficulty" className="sm:col-span-2">
                <Segmented ariaLabel="Difficulty" className="flex w-full" value={difficulty} options={DIFFICULTY_OPTIONS} onChange={setDifficulty} />
              </Field>
              <Field htmlFor={`${id}-count`} label="Number of questions" error={errors.count} hint={`1–${MAX_QUESTIONS} per generation`}>
                <Input
                  id={`${id}-count`}
                  type="number"
                  min={1}
                  max={MAX_QUESTIONS}
                  inputMode="numeric"
                  value={count}
                  invalid={!!errors.count}
                  onChange={(e) => setCount(e.target.value === "" ? "" : Number(e.target.value))}
                />
              </Field>
              <Field htmlFor={`${id}-category`} label="Audience / category" hint="e.g. Grade 10, university, interview prep">
                <Input id={`${id}-category`} value={category} maxLength={100} onChange={(e) => setCategory(e.target.value)} />
              </Field>
              <Field htmlFor={`${id}-instructions`} label="Extra instructions (optional)" className="sm:col-span-2">
                <Input
                  id={`${id}-instructions`}
                  value={instructions}
                  maxLength={500}
                  placeholder="e.g. Focus on practical scenarios; avoid trick questions"
                  onChange={(e) => setInstructions(e.target.value)}
                />
              </Field>
            </div>
          </Card>

          <Card className="p-4 sm:p-6">
            <h2 className="mb-4 text-base font-semibold">Exam settings</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field htmlFor={`${id}-title`} label="Test title (optional)" className="sm:col-span-2" hint="Defaults to “Subject - Topic”.">
                <Input id={`${id}-title`} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
              </Field>
              <Field htmlFor={`${id}-duration`} label="Duration (minutes)" error={errors.duration} hint="Default: 1 minute per question (min 5).">
                <Input
                  id={`${id}-duration`}
                  type="number"
                  min={1}
                  max={600}
                  inputMode="numeric"
                  value={duration}
                  placeholder="Auto"
                  invalid={!!errors.duration}
                  onChange={(e) => setDuration(e.target.value === "" ? "" : Number(e.target.value))}
                />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field htmlFor={`${id}-marks`} label="Marks" error={errors.marks}>
                  <Input
                    id={`${id}-marks`}
                    type="number"
                    min={0.25}
                    step={0.25}
                    inputMode="decimal"
                    value={marks}
                    invalid={!!errors.marks}
                    onChange={(e) => setMarks(e.target.value === "" ? "" : Number(e.target.value))}
                  />
                </Field>
                <Field htmlFor={`${id}-negative`} label="Negative" error={errors.negative}>
                  <Input
                    id={`${id}-negative`}
                    type="number"
                    min={0}
                    step={0.25}
                    inputMode="decimal"
                    value={negative}
                    invalid={!!errors.negative}
                    onChange={(e) => setNegative(e.target.value === "" ? "" : Number(e.target.value))}
                  />
                </Field>
              </div>
              <div className="sm:col-span-2">
                <Switch
                  label="AI quality review"
                  description="A second AI pass checks accuracy and wording. Slower and uses about twice the tokens."
                  checked={review}
                  onChange={setReview}
                />
              </div>
            </div>
          </Card>
        </fieldset>

        <div className="mt-6 flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-end">
          {busy && (
            <>
              <p className="flex-1 text-sm text-muted" aria-live="polite">
                {LOADING_MESSAGES[messageIndex]} This usually takes 10–60 seconds.
              </p>
              <Button variant="outline" onClick={() => abortRef.current?.abort()}>
                Cancel
              </Button>
            </>
          )}
          <Button type="submit" size="lg" loading={busy} disabled={!aiConfigured} icon={<Sparkles className="size-5" />}>
            {busy ? "Generating…" : "Generate questions"}
          </Button>
        </div>
      </form>
    </div>
  );
}
