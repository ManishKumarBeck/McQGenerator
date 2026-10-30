import { Clock, Copy, FileDown, FileQuestion, MoreVertical, Pencil, Play, RotateCcw, Sparkles, Trash2, Trophy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { formatMarks, formatPercent, formatRelative, pluralize, scoreTone } from "../../lib/format";
import type { TestSummary } from "../../lib/types";
import { Button, ButtonLink } from "../ui/Button";
import { Badge, Card, difficultyTone } from "../ui/primitives";

interface Props {
  test: TestSummary;
  onDuplicate: (test: TestSummary) => void;
  onDelete: (test: TestSummary) => void;
  onDownload: (test: TestSummary) => void;
}

export function TestCard({ test, onDuplicate, onDelete, onDownload }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent && menuRef.current?.contains(event.target as Node)) return;
      setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menuOpen]);

  const published = test.status === "published";
  const meta = [test.subject, test.topic].filter(Boolean).join(" · ");

  return (
    <Card className="flex flex-col p-4 transition-shadow hover:shadow-md sm:p-5" data-testid="test-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <Badge tone={published ? "success" : "warning"}>{published ? "Published" : "Draft"}</Badge>
            <Badge tone={difficultyTone(test.difficulty)} className="capitalize">
              {test.difficulty}
            </Badge>
            {test.source === "ai" && (
              <Badge tone="brand">
                <Sparkles className="size-3" /> AI
              </Badge>
            )}
          </div>
          <Link to={published ? `/tests/${test.id}` : `/tests/${test.id}/edit`} className="line-clamp-2 font-semibold text-fg hover:text-brand-600 dark:hover:text-brand-400">
            {test.title}
          </Link>
          {meta && <p className="mt-0.5 truncate text-sm text-muted">{meta}</p>}
        </div>
        <div className="relative" ref={menuRef}>
          <Button variant="ghost" size="icon" aria-label={`More actions for ${test.title}`} aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
            <MoreVertical className="size-4" />
          </Button>
          {menuOpen && (
            <div role="menu" className="absolute right-0 z-10 mt-1 w-44 animate-pop overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-lg">
              <Link role="menuitem" to={`/tests/${test.id}/edit`} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-surface-2">
                <Pencil className="size-4" /> Edit
              </Link>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2"
                onClick={() => {
                  setMenuOpen(false);
                  onDuplicate(test);
                }}
              >
                <Copy className="size-4" /> Duplicate
              </button>
              <button
                role="menuitem"
                disabled={test.question_count === 0}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setMenuOpen(false);
                  onDownload(test);
                }}
              >
                <FileDown className="size-4" /> Download PDF
              </button>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete(test);
                }}
              >
                <Trash2 className="size-4" /> Delete
              </button>
            </div>
          )}
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
        <div>
          <dt className="flex items-center gap-1 text-xs text-muted">
            <FileQuestion className="size-3.5" /> Questions
          </dt>
          <dd className="font-medium tabular-nums">{test.question_count}</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-xs text-muted">
            <Clock className="size-3.5" /> Duration
          </dt>
          <dd className="font-medium tabular-nums">{test.duration_minutes} min</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-xs text-muted">
            <Trophy className="size-3.5" /> Best
          </dt>
          <dd className="font-medium tabular-nums">
            {test.best_percentage === null ? (
              "—"
            ) : (
              <span className={scoreTone(test.best_percentage) === "danger" ? "text-rose-600 dark:text-rose-400" : scoreTone(test.best_percentage) === "success" ? "text-emerald-600 dark:text-emerald-400" : ""}>
                {formatPercent(test.best_percentage, 0)}
              </span>
            )}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted">
        +{formatMarks(test.marks_per_question)} / {test.negative_marks > 0 ? `−${formatMarks(test.negative_marks)}` : "no negative marking"} ·{" "}
        {test.attempt_count > 0 ? `${pluralize(test.attempt_count, "attempt")} · last ${formatRelative(test.last_attempt_at)}` : "Not attempted yet"}
      </p>

      <div className="mt-4 flex gap-2 border-t border-line pt-4">
        {published ? (
          <ButtonLink
            className="flex-1"
            to={test.in_progress_attempt_id ? `/attempts/${test.in_progress_attempt_id}` : `/tests/${test.id}`}
            icon={test.in_progress_attempt_id ? <RotateCcw className="size-4" /> : <Play className="size-4" />}
            variant={test.in_progress_attempt_id ? "success" : "primary"}
          >
            {test.in_progress_attempt_id ? "Resume" : "Start test"}
          </ButtonLink>
        ) : (
          <ButtonLink to={`/tests/${test.id}/edit`} className="flex-1" variant="outline" icon={<Pencil className="size-4" />}>
            Review & publish
          </ButtonLink>
        )}
      </div>
    </Card>
  );
}
