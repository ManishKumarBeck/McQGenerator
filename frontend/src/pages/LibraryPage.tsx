import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  BookOpen,
  FileText,
  Globe,
  Library,
  Link2,
  Loader2,
  MoreVertical,
  Pencil,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button, ButtonLink } from "../components/ui/Button";
import { ConfirmDialog, Modal } from "../components/ui/Modal";
import { Badge, Card, EmptyState, ErrorState, Field, Input, PageHeader, ProgressBar, Segmented, Skeleton, Spinner } from "../components/ui/primitives";
import { api, ApiError } from "../lib/api";
import { formatRelative, pluralize } from "../lib/format";
import type { SourceItem } from "../lib/types";

const ACCEPTED = [".pdf", ".docx", ".txt", ".md", ".epub"];
const MAX_MB = 25;

const errorMessage = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

export function LibraryPage() {
  const queryClient = useQueryClient();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: api.listSources,
    // Poll while anything is still being indexed.
    refetchInterval: (query) => (query.state.data?.some((s) => s.status === "processing") ? 1500 : false),
  });
  const [toDelete, setToDelete] = useState<SourceItem | null>(null);
  const [toRename, setToRename] = useState<SourceItem | null>(null);
  const [toSearch, setToSearch] = useState<SourceItem | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["sources"] });

  const remove = useMutation({
    mutationFn: (source: SourceItem) => api.deleteSource(source.id),
    onSuccess: () => {
      invalidate();
      toast.success("Source deleted");
      setToDelete(null);
    },
    onError: (error) => toast.error(errorMessage(error, "Could not delete the source.")),
  });

  const reindex = useMutation({
    mutationFn: (source: SourceItem) => api.reindexSource(source.id),
    onSuccess: () => {
      invalidate();
      toast.info("Re-indexing started");
    },
    onError: (error) => toast.error(errorMessage(error, "Could not re-index the source.")),
  });

  return (
    <>
      <PageHeader
        title="Library"
        description="Add books, documents and web pages once, then generate tests from them. Questions are based on the most relevant passages and cite where they came from."
      />

      <AddSourcePanel onAdded={invalidate} />

      <section className="mt-8" aria-labelledby="sources-heading">
        <h2 id="sources-heading" className="mb-3 text-lg font-semibold">
          Your sources {sources.data && <span className="text-muted">({sources.data.length})</span>}
        </h2>
        {sources.isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-24 rounded-2xl" />
            ))}
          </div>
        ) : sources.isError ? (
          <Card>
            <ErrorState error={sources.error} onRetry={() => sources.refetch()} title="Couldn't load the library" />
          </Card>
        ) : sources.data.length === 0 ? (
          <Card>
            <EmptyState
              icon={<Library className="size-6" />}
              title="Your library is empty"
              description="Upload a textbook, lecture notes or an e-book, or paste a link to an article. It's indexed once and reusable for every test."
            />
          </Card>
        ) : (
          <div className="space-y-3">
            {sources.data.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                onDelete={setToDelete}
                onRename={setToRename}
                onSearch={setToSearch}
                onReindex={(s) => reindex.mutate(s)}
              />
            ))}
          </div>
        )}
      </section>

      <ConfirmDialog
        open={toDelete !== null}
        title={`Delete “${toDelete?.title ?? ""}”?`}
        description="Its indexed text is removed from the library. Tests already generated from it are not affected."
        confirmLabel="Delete source"
        tone="danger"
        loading={remove.isPending}
        onCancel={() => setToDelete(null)}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
      />
      {toRename && <RenameDialog source={toRename} onClose={() => setToRename(null)} onDone={invalidate} />}
      {toSearch && <SearchDialog source={toSearch} onClose={() => setToSearch(null)} />}
    </>
  );
}

// --------------------------------------------------------------------------- add panel

function AddSourcePanel({ onAdded }: { onAdded: () => void }) {
  const id = useId();
  const [mode, setMode] = useState<"file" | "url">("file");
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadSource(file);
      return files.length;
    },
    onSuccess: (count) => {
      onAdded();
      toast.success(count === 1 ? "Uploaded — indexing in the background" : `${count} files uploaded — indexing in the background`);
    },
    onError: (error) => {
      onAdded();
      toast.error(errorMessage(error, "Upload failed."));
    },
  });

  const addLink = useMutation({
    mutationFn: () => api.addUrlSource(url.trim(), title.trim()),
    onSuccess: () => {
      onAdded();
      setUrl("");
      setTitle("");
      toast.success("Link added — downloading and indexing");
    },
    onError: (error) => setUrlError(errorMessage(error, "Could not add the link.")),
  });

  const pickFiles = (list: FileList | null | undefined) => {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    for (const file of files) {
      const lower = file.name.toLowerCase();
      if (!ACCEPTED.some((ext) => lower.endsWith(ext))) return setFileError(`“${file.name}” isn't a supported file type.`);
      if (file.size > MAX_MB * 1024 * 1024) return setFileError(`“${file.name}” is larger than ${MAX_MB} MB.`);
      if (file.size === 0) return setFileError(`“${file.name}” is empty.`);
    }
    setFileError(null);
    upload.mutate(files);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    pickFiles(event.dataTransfer.files);
  };

  const submitLink = (event: FormEvent) => {
    event.preventDefault();
    try {
      const parsed = new URL(url.trim());
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      setUrlError("Enter a full web address starting with http:// or https://");
      return;
    }
    setUrlError(null);
    addLink.mutate();
  };

  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-base font-semibold">Add a source</h2>
        <Segmented
          ariaLabel="Source type"
          value={mode}
          onChange={setMode}
          options={[
            { value: "file", label: "Upload files" },
            { value: "url", label: "Add a link" },
          ]}
        />
      </div>

      {mode === "file" ? (
        <>
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={clsx(
              "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
              dragging ? "border-brand-500 bg-brand-50 dark:bg-brand-500/10" : fileError ? "border-rose-400" : "border-line hover:border-brand-400",
              upload.isPending && "pointer-events-none opacity-60",
            )}
          >
            {upload.isPending ? <Loader2 className="mb-2 size-6 animate-spin text-brand-500" /> : <Upload className="mb-2 size-6 text-muted" />}
            <span className="text-sm font-medium">{upload.isPending ? "Uploading…" : "Drop books or documents here, or click to browse"}</span>
            <span className="mt-1 text-xs text-muted">PDF, Word (.docx), EPUB, TXT or Markdown · up to {MAX_MB} MB each · text-based PDFs only</span>
            <input
              type="file"
              multiple
              accept={ACCEPTED.join(",")}
              className="sr-only"
              data-testid="source-file-input"
              onChange={(e) => {
                pickFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
          {fileError && <p className="mt-1.5 text-xs font-medium text-rose-600 dark:text-rose-400">{fileError}</p>}
        </>
      ) : (
        <form onSubmit={submitLink} noValidate className="grid gap-4 sm:grid-cols-[1fr_240px_auto] sm:items-start">
          <Field htmlFor={`${id}-url`} label="Web address" error={urlError} hint="An article, documentation page or a direct link to a PDF.">
            <Input
              id={`${id}-url`}
              type="url"
              inputMode="url"
              value={url}
              invalid={!!urlError}
              placeholder="https://en.wikipedia.org/wiki/Photosynthesis"
              onChange={(e) => setUrl(e.target.value)}
            />
          </Field>
          <Field htmlFor={`${id}-title`} label="Title (optional)">
            <Input id={`${id}-title`} value={title} maxLength={300} placeholder="Uses the page title" onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Button type="submit" className="sm:mt-7" loading={addLink.isPending} icon={<Link2 className="size-4" />} disabled={!url.trim()}>
            Add link
          </Button>
        </form>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------------- source card

function sourceIcon(source: SourceItem) {
  if (source.kind === "url") return <Globe className="size-5" />;
  if (source.file_type === "epub") return <BookOpen className="size-5" />;
  return <FileText className="size-5" />;
}

function describe(source: SourceItem) {
  const parts: string[] = [source.kind === "url" ? hostname(source.origin) : source.file_type.toUpperCase()];
  if (source.page_count) parts.push(`${source.page_count.toLocaleString()} pages`);
  if (source.char_count) parts.push(`~${Math.max(1, Math.round(source.char_count / 6 / 100) * 100).toLocaleString()} words`);
  if (source.chunk_count) parts.push(pluralize(source.chunk_count, "passage"));
  parts.push(`added ${formatRelative(source.created_at)}`);
  return parts.join(" · ");
}

function hostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "link";
  }
}

function SourceCard({
  source,
  onDelete,
  onRename,
  onSearch,
  onReindex,
}: {
  source: SourceItem;
  onDelete: (s: SourceItem) => void;
  onRename: (s: SourceItem) => void;
  onSearch: (s: SourceItem) => void;
  onReindex: (s: SourceItem) => void;
}) {
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

  const ready = source.status === "ready";
  const menuItem = "flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <Card className="p-4 sm:p-5" data-testid="source-card">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
          {sourceIcon(source)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {source.kind === "url" ? (
              <a href={source.origin} target="_blank" rel="noreferrer" className="truncate font-semibold hover:text-brand-600 dark:hover:text-brand-400" title={source.origin}>
                {source.title}
              </a>
            ) : (
              <p className="truncate font-semibold" title={source.origin}>
                {source.title}
              </p>
            )}
            {source.status === "processing" && <Badge tone="info">Indexing</Badge>}
            {source.status === "failed" && <Badge tone="danger">Failed</Badge>}
            {ready && (
              <Badge tone={source.semantic_search ? "brand" : "neutral"} title={source.semantic_search ? "Finds passages by meaning (embeddings)" : "Matches exact keywords only"}>
                {source.semantic_search ? "Semantic search" : "Keyword search"}
              </Badge>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{describe(source)}</p>

          {source.status === "processing" && (
            <div className="mt-3 flex items-center gap-3">
              <ProgressBar value={source.progress} label={`Indexing ${source.title}`} className="max-w-sm" />
              <span className="text-xs text-muted tabular-nums">{source.progress}%</span>
            </div>
          )}
          {source.status === "failed" && (
            <p className="mt-2 flex items-start gap-1.5 text-sm text-rose-600 dark:text-rose-400">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {source.error}
            </p>
          )}
          {ready && source.notes && <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">{source.notes}</p>}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {ready && (
            <div className="hidden sm:block">
              <ButtonLink to={`/tests/new?source=${source.id}`} size="sm" icon={<Sparkles className="size-3.5" />}>
                Generate test
              </ButtonLink>
            </div>
          )}
          {source.status === "failed" && (
            <Button size="sm" variant="outline" icon={<RefreshCw className="size-3.5" />} onClick={() => onReindex(source)}>
              Retry
            </Button>
          )}
          <div className="relative" ref={menuRef}>
            <Button variant="ghost" size="icon" aria-label={`More actions for ${source.title}`} aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
              <MoreVertical className="size-4" />
            </Button>
            {menuOpen && (
              <div role="menu" className="absolute right-0 z-10 mt-1 w-48 animate-pop overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-lg">
                {ready && (
                  <Link role="menuitem" to={`/tests/new?source=${source.id}`} className={clsx(menuItem, "sm:hidden")}>
                    <Sparkles className="size-4" /> Generate test
                  </Link>
                )}
                <button role="menuitem" className={menuItem} disabled={!ready} onClick={() => (setMenuOpen(false), onSearch(source))}>
                  <Search className="size-4" /> Search inside
                </button>
                <button role="menuitem" className={menuItem} onClick={() => (setMenuOpen(false), onRename(source))}>
                  <Pencil className="size-4" /> Rename
                </button>
                <button role="menuitem" className={menuItem} disabled={source.status === "processing"} onClick={() => (setMenuOpen(false), onReindex(source))}>
                  <RefreshCw className="size-4" /> Re-index
                </button>
                <button
                  role="menuitem"
                  className={clsx(menuItem, "text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10")}
                  onClick={() => (setMenuOpen(false), onDelete(source))}
                >
                  <Trash2 className="size-4" /> Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

// --------------------------------------------------------------------------- dialogs

function RenameDialog({ source, onClose, onDone }: { source: SourceItem; onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState(source.title);
  const rename = useMutation({
    mutationFn: () => api.renameSource(source.id, title.trim()),
    onSuccess: () => {
      onDone();
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error, "Could not rename the source.")),
  });
  return (
    <Modal
      open
      onClose={onClose}
      title="Rename source"
      description="The title appears in question citations."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => rename.mutate()} loading={rename.isPending} disabled={!title.trim()}>
            Save
          </Button>
        </>
      }
    >
      <Input aria-label="Source title" value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} autoFocus />
    </Modal>
  );
}

function SearchDialog({ source, onClose }: { source: SourceItem; onClose: () => void }) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const results = useQuery({
    queryKey: ["source-search", source.id, query],
    queryFn: () => api.searchSource(source.id, query),
    enabled: query.length > 0,
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={`Search “${source.title}”`}
      description="See which passages would be used for a topic — this is the retrieval step behind generation."
      className="max-h-[90dvh] overflow-y-auto"
    >
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(input.trim());
        }}
      >
        <Input aria-label="Search query" value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. cell division" autoFocus />
        <Button type="submit" disabled={!input.trim()} icon={<Search className="size-4" />}>
          Search
        </Button>
      </form>
      <div className="mt-4 space-y-3" aria-live="polite">
        {results.isFetching ? (
          <Spinner label="Searching…" />
        ) : results.isError ? (
          <p className="text-sm text-rose-600">{errorMessage(results.error, "Search failed.")}</p>
        ) : results.data && results.data.length === 0 ? (
          <p className="text-sm text-muted">No passages match. Try other words.</p>
        ) : (
          results.data?.map((hit) => (
            <div key={hit.position} className="rounded-xl border border-line p-3" data-testid="search-hit">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold">{hit.citation}</span>
                {hit.semantic_score !== null && <Badge tone="brand">similarity {Math.round(hit.semantic_score * 100)}%</Badge>}
                {hit.keyword_score > 0 && <Badge>keywords {hit.keyword_score.toFixed(1)}</Badge>}
              </div>
              <p className="line-clamp-4 text-sm text-muted">{hit.text}</p>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
}
