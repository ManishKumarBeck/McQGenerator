import { useId } from "react";
import type { DraftErrors, DraftTest } from "../../lib/testDraft";
import type { Difficulty } from "../../lib/types";
import { Card, Field, Input, Segmented, Switch, Textarea } from "../ui/primitives";

export const DIFFICULTY_OPTIONS: { value: Difficulty; label: string }[] = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
  { value: "mixed", label: "Mixed" },
];

const numberOrEmpty = (value: string): number | "" => (value === "" ? "" : Number(value));

export function TestSettingsForm({
  draft,
  errors,
  showErrors,
  onChange,
}: {
  draft: DraftTest;
  errors: DraftErrors["fields"];
  showErrors: boolean;
  onChange: (patch: Partial<DraftTest>) => void;
}) {
  const id = useId();
  const err = (key: keyof DraftErrors["fields"]) => (showErrors ? errors[key] : undefined);

  return (
    <Card className="p-4 sm:p-6">
      <h2 className="mb-4 text-base font-semibold">Test details</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field htmlFor={`${id}-title`} label="Title" required error={err("title")} className="sm:col-span-2">
          <Input
            id={`${id}-title`}
            value={draft.title}
            maxLength={200}
            invalid={!!err("title")}
            placeholder="e.g. Data Structures – Unit 2 quiz"
            onChange={(e) => onChange({ title: e.target.value })}
          />
        </Field>
        <Field htmlFor={`${id}-description`} label="Description / instructions" className="sm:col-span-2">
          <Textarea
            id={`${id}-description`}
            rows={2}
            maxLength={2000}
            value={draft.description}
            placeholder="Optional notes shown before the test starts."
            onChange={(e) => onChange({ description: e.target.value })}
          />
        </Field>
        <Field htmlFor={`${id}-subject`} label="Subject">
          <Input id={`${id}-subject`} maxLength={100} value={draft.subject} placeholder="e.g. Computer Science" onChange={(e) => onChange({ subject: e.target.value })} />
        </Field>
        <Field htmlFor={`${id}-topic`} label="Topic">
          <Input id={`${id}-topic`} maxLength={150} value={draft.topic} placeholder="e.g. Stacks & Queues" onChange={(e) => onChange({ topic: e.target.value })} />
        </Field>
        <Field htmlFor={`${id}-category`} label="Category" hint="Audience or exam, e.g. Grade 10, GATE, Interview prep.">
          <Input id={`${id}-category`} maxLength={100} value={draft.category} onChange={(e) => onChange({ category: e.target.value })} />
        </Field>
        <Field label="Difficulty">
          <Segmented ariaLabel="Difficulty" className="flex w-full" value={draft.difficulty} options={DIFFICULTY_OPTIONS} onChange={(difficulty) => onChange({ difficulty })} />
        </Field>
      </div>

      <h2 className="mt-8 mb-4 text-base font-semibold">Timing & marking</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field htmlFor={`${id}-duration`} label="Duration (minutes)" required error={err("duration_minutes")}>
          <Input
            id={`${id}-duration`}
            type="number"
            inputMode="numeric"
            min={1}
            max={600}
            step={1}
            value={draft.duration_minutes}
            invalid={!!err("duration_minutes")}
            onChange={(e) => onChange({ duration_minutes: numberOrEmpty(e.target.value) })}
          />
        </Field>
        <Field htmlFor={`${id}-marks`} label="Marks per correct answer" required error={err("marks_per_question")}>
          <Input
            id={`${id}-marks`}
            type="number"
            inputMode="decimal"
            min={0.25}
            max={100}
            step={0.25}
            value={draft.marks_per_question}
            invalid={!!err("marks_per_question")}
            onChange={(e) => onChange({ marks_per_question: numberOrEmpty(e.target.value) })}
          />
        </Field>
        <Field
          htmlFor={`${id}-negative`}
          label="Negative marks per wrong answer"
          error={err("negative_marks")}
          hint="0 disables negative marking. Unanswered questions score 0."
        >
          <Input
            id={`${id}-negative`}
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            step={0.25}
            value={draft.negative_marks}
            invalid={!!err("negative_marks")}
            onChange={(e) => onChange({ negative_marks: numberOrEmpty(e.target.value) })}
          />
        </Field>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Switch
          label="Shuffle question order"
          description="Each attempt gets a different order."
          checked={draft.shuffle_questions}
          onChange={(shuffle_questions) => onChange({ shuffle_questions })}
        />
        <Switch
          label="Shuffle answer options"
          description="Randomises A–D positions per attempt."
          checked={draft.shuffle_options}
          onChange={(shuffle_options) => onChange({ shuffle_options })}
        />
      </div>
    </Card>
  );
}
