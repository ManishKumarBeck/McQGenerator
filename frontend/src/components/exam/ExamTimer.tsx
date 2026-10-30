import clsx from "clsx";
import { Timer } from "lucide-react";
import { formatClock } from "../../lib/format";

export function ExamTimer({ remaining, total }: { remaining: number | null; total: number }) {
  const seconds = remaining ?? total;
  const critical = seconds <= 60;
  const warning = !critical && seconds <= 300;
  return (
    <div
      role="timer"
      aria-label={`Time remaining ${formatClock(seconds)}`}
      className={clsx(
        "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 font-mono text-sm font-semibold tabular-nums transition-colors sm:text-base",
        critical
          ? "animate-pulse border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-300"
          : warning
            ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300"
            : "border-line bg-surface-2 text-fg",
      )}
    >
      <Timer className="size-4" aria-hidden />
      <span data-testid="timer">{formatClock(seconds)}</span>
    </div>
  );
}
