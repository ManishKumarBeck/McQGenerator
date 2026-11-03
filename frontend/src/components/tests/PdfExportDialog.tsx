import { useMutation, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { api, ApiError } from "../../lib/api";
import { readString, writeString } from "../../lib/storage";
import type { PdfExportOptions } from "../../lib/types";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { ErrorState, Field, Input, Spinner, Switch, Textarea } from "../ui/primitives";

interface Props {
  testId: number;
  open: boolean;
  onClose: () => void;
}

/** Modal form for downloading a test as a printable PDF with a custom heading. */
export function PdfExportDialog({ testId, open, onClose }: Props) {
  const defaults = useQuery({
    queryKey: ["pdf-defaults", testId],
    queryFn: () => api.pdfDefaults(testId),
    enabled: open,
    staleTime: 0,
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Download as PDF"
      description="Customise the heading and choose what to include in the printable paper."
      className="max-h-[92dvh] overflow-y-auto"
    >
      {defaults.isPending ? (
        <Spinner label="Preparing…" />
      ) : defaults.isError ? (
        <ErrorState error={defaults.error} onRetry={() => defaults.refetch()} />
      ) : (
        // Re-mount the form for each opening so it starts from fresh defaults.
        <ExportForm key={defaults.dataUpdatedAt} testId={testId} defaults={defaults.data} onDone={onClose} />
      )}
    </Modal>
  );
}

function ExportForm({ testId, defaults, onDone }: { testId: number; defaults: PdfExportOptions; onDone: () => void }) {
  const id = useId();
  const [options, setOptions] = useState<PdfExportOptions>(() => ({
    ...defaults,
    institution: readString("pdf:institution") ?? defaults.institution,
  }));
  const set = <K extends keyof PdfExportOptions>(key: K, value: PdfExportOptions[K]) =>
    setOptions((current) => ({ ...current, [key]: value }));

  const download = useMutation({
    mutationFn: () => api.downloadPdf(testId, options),
    onSuccess: ({ blob, filename }) => {
      writeString("pdf:institution", options.institution.trim());
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
      toast.success(`Downloaded ${filename}`);
      onDone();
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not create the PDF."),
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    download.mutate();
  };

  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={download.isPending} className="min-w-0 space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field htmlFor={`${id}-institution`} label="Institution / organisation" className="sm:col-span-2" hint="Shown at the very top. Remembered for next time.">
            <Input
              id={`${id}-institution`}
              value={options.institution}
              maxLength={150}
              placeholder="e.g. Springfield High School"
              onChange={(e) => set("institution", e.target.value)}
            />
          </Field>
          <Field htmlFor={`${id}-title`} label="Test heading" className="sm:col-span-2">
            <Input id={`${id}-title`} value={options.title} maxLength={200} onChange={(e) => set("title", e.target.value)} />
          </Field>
          <Field htmlFor={`${id}-subtitle`} label="Subtitle" hint="e.g. subject, class or exam name">
            <Input id={`${id}-subtitle`} value={options.subtitle} maxLength={200} onChange={(e) => set("subtitle", e.target.value)} />
          </Field>
          <Field htmlFor={`${id}-date`} label="Exam date">
            <Input id={`${id}-date`} value={options.exam_date} maxLength={50} placeholder="e.g. 12 Nov 2026" onChange={(e) => set("exam_date", e.target.value)} />
          </Field>
          <Field htmlFor={`${id}-instructions`} label="Instructions" className="sm:col-span-2" hint="One instruction per line. Leave empty to omit.">
            <Textarea
              id={`${id}-instructions`}
              rows={4}
              maxLength={3000}
              value={options.instructions}
              onChange={(e) => set("instructions", e.target.value)}
            />
          </Field>
        </div>

        <div className="space-y-4 rounded-xl border border-line p-4">
          <h3 className="text-sm font-semibold">Layout</h3>
          <Switch label="Exam details" description="Date, duration, total marks and marking scheme." checked={options.show_details} onChange={(v) => set("show_details", v)} />
          <Switch label="Student fields" description="Blank Name, Roll No. and Signature lines." checked={options.student_fields} onChange={(v) => set("student_fields", v)} />
          <Switch label="Answer sheet" description="An extra page with fill-in bubbles for each question." checked={options.include_answer_sheet} onChange={(v) => set("include_answer_sheet", v)} />
          <Switch label="Answer key" description="Correct answers on a separate page at the end." checked={options.include_answer_key} onChange={(v) => set("include_answer_key", v)} />
          <Switch
            label="Explanations in the key"
            description="Adds each question's explanation below the answer key."
            checked={options.include_explanations && options.include_answer_key}
            disabled={!options.include_answer_key}
            onChange={(v) => set("include_explanations", v)}
          />
        </div>

        <div className="space-y-4 rounded-xl border border-line p-4">
          <h3 className="text-sm font-semibold">Paper version</h3>
          <Switch label="Shuffle question order" checked={options.shuffle_questions} onChange={(v) => set("shuffle_questions", v)} />
          <Switch label="Shuffle answer options" checked={options.shuffle_options} onChange={(v) => set("shuffle_options", v)} />
          <Field
            htmlFor={`${id}-version`}
            label="Version label"
            hint="e.g. Set A / Set B. Each label gives its own fixed shuffle, so you can print several versions that always match their answer key."
          >
            <Input id={`${id}-version`} value={options.version_label} maxLength={20} placeholder="Optional" onChange={(e) => set("version_label", e.target.value)} />
          </Field>
        </div>
      </fieldset>

      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant="outline" onClick={onDone} disabled={download.isPending}>
          Cancel
        </Button>
        <Button type="submit" loading={download.isPending} icon={<Download className="size-4" />}>
          Download PDF
        </Button>
      </div>
    </form>
  );
}
