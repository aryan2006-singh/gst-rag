import type { Citation } from "../types";

const STATUS_STYLES: Record<Citation["status"], string> = {
  in_force:
    "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300",
  amended:
    "border-amber-500 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300",
  superseded:
    "border-red-500 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300",
  unknown:
    "border-slate-400 bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-400",
};

export default function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="rounded-lg border-l-4 border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[citation.status]}`}>
          {citation.status}
        </span>
        <span className="font-semibold text-slate-800 dark:text-slate-100">{citation.doc_id}</span>
        {citation.section && (
          <span className="text-slate-500 dark:text-slate-400">section {citation.section}</span>
        )}
        <span className="ml-auto font-mono text-xs text-slate-400">
          score {citation.score.toFixed(3)}
          {citation.published ? ` · ${citation.published}` : ""}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {citation.snippet}
      </p>
    </div>
  );
}
