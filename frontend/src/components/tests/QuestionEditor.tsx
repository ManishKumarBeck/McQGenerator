import clsx from "clsx";
import { ArrowDown, ArrowUp, Check, Copy, Plus, Trash2, X } from "lucide-react";
import { useId } from "react";
import { OPTION_LABELS } from "../../lib/format";
import { MAX_OPTIONS, MIN_OPTIONS, type DraftQuestion, type QuestionErrors } from "../../lib/testDraft";
import { Button } from "../ui/Button";
import { Card, Field, Input, Textarea } from "../ui/primitives";

interface Props {
  index: number;
  total: number;
  question: DraftQuestion;
  errors?: QuestionErrors;
  showErrors: boolean;
  onChange: (question: DraftQuestion) => void;
  onMove: (direction: -1 | 1) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}

export function QuestionEditor({ index, total, question, errors, showErrors, onChange, onMove, onDuplicate, onRemove }: Props) {
  const id = useId();
  const visibleErrors = showErrors ? errors : undefined;
  const update = (patch: Partial<DraftQuestion>) => onChange({ ...question, ...patch });

  const setOption = (optionIndex: number, value: string) => {
    const options = [...question.options];
    options[optionIndex] = value;
    update({ options });
  };

  const removeOption = (optionIndex: number) => {
    const options = question.options.filter((_, i) => i !== optionIndex);
    let correct = question.correct_option;
    if (optionIndex === correct) correct = 0;
    else if (optionIndex < correct) correct -= 1;
    update({ options, correct_option: correct });
  };

  return (
    <Card
      id={`question-${question.key}`}
      className={clsx("p-4 sm:p-5", visibleErrors && "border-rose-300 dark:border-rose-500/50")}
      data-testid="question-editor"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-fg">Question {index + 1}</h3>
        <div className="flex items-center gap-0.5">
          <Button variant="ghost" size="icon" onClick={() => onMove(-1)} disabled={index === 0} aria-label={`Move question ${index + 1} up`}>
            <ArrowUp className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => onMove(1)} disabled={index === total - 1} aria-label={`Move question ${index + 1} down`}>
            <ArrowDown className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDuplicate} aria-label={`Duplicate question ${index + 1}`}>
            <Copy className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onRemove} aria-label={`Delete question ${index + 1}`} className="hover:text-rose-600">
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <Field htmlFor={`${id}-text`} error={visibleErrors?.text} label="Question" required>
        <Textarea
          id={`${id}-text`}
          rows={2}
          value={question.text}
          maxLength={2000}
          invalid={!!visibleErrors?.text}
          placeholder="e.g. Which data structure uses first-in, first-out ordering?"
          onChange={(e) => update({ text: e.target.value })}
        />
      </Field>

      <fieldset className="mt-4">
        <legend className="mb-2 text-sm font-medium text-fg">
          Options <span className="font-normal text-muted">— select the correct answer</span>
        </legend>
        <div className="space-y-2">
          {question.options.map((option, optionIndex) => {
            const isCorrect = question.correct_option === optionIndex;
            const optionError = visibleErrors?.options?.[optionIndex];
            return (
              <div key={optionIndex}>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    role="radio"
                    aria-checked={isCorrect}
                    aria-label={`Mark option ${OPTION_LABELS[optionIndex]} as correct`}
                    onClick={() => update({ correct_option: optionIndex })}
                    className={clsx(
                      "flex size-9 shrink-0 items-center justify-center rounded-lg border text-sm font-semibold transition-colors",
                      isCorrect
                        ? "border-emerald-500 bg-emerald-500 text-white"
                        : "border-line bg-surface-2 text-muted hover:border-emerald-400",
                    )}
                  >
                    {isCorrect ? <Check className="size-4" /> : OPTION_LABELS[optionIndex]}
                  </button>
                  <Input
                    value={option}
                    maxLength={500}
                    invalid={!!optionError}
                    aria-label={`Option ${OPTION_LABELS[optionIndex]}`}
                    placeholder={`Option ${OPTION_LABELS[optionIndex]}`}
                    onChange={(e) => setOption(optionIndex, e.target.value)}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeOption(optionIndex)}
                    disabled={question.options.length <= MIN_OPTIONS}
                    aria-label={`Remove option ${OPTION_LABELS[optionIndex]}`}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
                {optionError && <p className="mt-1 ml-11 text-xs font-medium text-rose-600 dark:text-rose-400">{optionError}</p>}
              </div>
            );
          })}
        </div>
        {visibleErrors?.general && <p className="mt-2 text-xs font-medium text-rose-600 dark:text-rose-400">{visibleErrors.general}</p>}
        {question.options.length < MAX_OPTIONS && (
          <Button variant="ghost" size="sm" className="mt-2" icon={<Plus className="size-4" />} onClick={() => update({ options: [...question.options, ""] })}>
            Add option
          </Button>
        )}
      </fieldset>

      <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_200px]">
        <Field htmlFor={`${id}-explanation`} label="Explanation" hint="Shown to students when they review their results.">
          <Textarea
            id={`${id}-explanation`}
            rows={2}
            maxLength={3000}
            value={question.explanation}
            placeholder="Why is this the correct answer?"
            onChange={(e) => update({ explanation: e.target.value })}
          />
        </Field>
        <Field htmlFor={`${id}-topic`} label="Topic" hint="Used for topic-wise analytics.">
          <Input id={`${id}-topic`} maxLength={150} value={question.topic} placeholder="e.g. Queues" onChange={(e) => update({ topic: e.target.value })} />
        </Field>
      </div>
    </Card>
  );
}
