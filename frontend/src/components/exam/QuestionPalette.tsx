import clsx from "clsx";
import { paletteStatus, type AnswerMap, type ExamSummary, type PaletteStatus } from "../../lib/exam";

const styles: Record<PaletteStatus, string> = {
  answered: "bg-emerald-500 border-emerald-500 text-white",
  unanswered: "bg-rose-50 border-rose-300 text-rose-700 dark:bg-rose-500/10 dark:border-rose-500/40 dark:text-rose-300",
  marked: "bg-violet-500 border-violet-500 text-white",
  "answered-marked": "bg-violet-500 border-violet-500 text-white",
  "not-visited": "bg-surface border-line text-muted",
};

const labels: Record<PaletteStatus, string> = {
  answered: "Answered",
  unanswered: "Not answered",
  marked: "Marked for review",
  "answered-marked": "Answered & marked",
  "not-visited": "Not visited",
};

export function QuestionPalette({
  total,
  answers,
  visited,
  current,
  summary,
  onSelect,
}: {
  total: number;
  answers: AnswerMap;
  visited: Set<number>;
  current: number;
  summary: ExamSummary;
  onSelect: (position: number) => void;
}) {
  return (
    <div>
      <div className="mb-4 grid grid-cols-3 gap-2 text-center">
        <Count label="Answered" value={summary.answered} className="text-emerald-600 dark:text-emerald-400" />
        <Count label="Unanswered" value={summary.unanswered} className="text-rose-600 dark:text-rose-400" />
        <Count label="Marked" value={summary.marked} className="text-violet-600 dark:text-violet-400" />
      </div>
      <nav aria-label="Question palette">
        <ol className="grid grid-cols-5 gap-2 sm:grid-cols-6 lg:grid-cols-5">
          {Array.from({ length: total }, (_, position) => {
            const status = paletteStatus(answers[position], visited.has(position));
            const isCurrent = position === current;
            return (
              <li key={position}>
                <button
                  type="button"
                  onClick={() => onSelect(position)}
                  aria-current={isCurrent ? "step" : undefined}
                  aria-label={`Question ${position + 1}: ${labels[status]}`}
                  data-status={status}
                  className={clsx(
                    "relative flex aspect-square w-full items-center justify-center rounded-lg border text-sm font-semibold tabular-nums transition-transform hover:scale-105",
                    styles[status],
                    isCurrent && "ring-2 ring-brand-500 ring-offset-2 ring-offset-surface",
                  )}
                >
                  {position + 1}
                  {status === "answered-marked" && (
                    <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-surface bg-emerald-400" aria-hidden />
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      <ul className="mt-4 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-muted">
        {(["answered", "unanswered", "marked", "answered-marked", "not-visited"] as PaletteStatus[]).map((status) => (
          <li key={status} className="flex items-center gap-1.5">
            <span className={clsx("relative size-3 shrink-0 rounded border", styles[status])}>
              {status === "answered-marked" && <span className="absolute -right-0.5 -bottom-0.5 size-1.5 rounded-full bg-emerald-400" />}
            </span>
            {labels[status]}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Count({ label, value, className }: { label: string; value: number; className?: string }) {
  return (
    <div className="rounded-xl bg-surface-2 px-2 py-2">
      <div className={clsx("text-lg font-bold tabular-nums", className)}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}
