import type { Citation } from "../types";

const STATUS: Record<Citation["status"], { label: string; dot: string }> = {
  in_force: { label: "In force", dot: "bg-emerald-500" },
  amended: { label: "Amended", dot: "bg-amber" },
  superseded: { label: "Superseded", dot: "bg-red-500" },
  unknown: { label: "Status unknown", dot: "bg-neutral-400" },
};

const ACRONYMS = new Set(["cgst", "sgst", "igst", "utgst", "gst", "itc", "rcm", "faq", "faqs", "cbic", "gstr", "e"]);

function prettyDoc(docId: string) {
  return docId
    .replace(/^(rules|faq|circular|notification|instruction)-/, "")
    .split("-")
    .map((word) => (ACRONYMS.has(word) ? word.toUpperCase() : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(" ");
}

function tidy(snippet: string) {
  return snippet.replace(/#{2,}\s*/g, "").replace(/\n\s*\n+/g, "\n").trim();
}

export default function CitationCard({ citation, rank }: { citation: Citation; rank: number }) {
  const status = STATUS[citation.status] ?? STATUS.unknown;
  const stages = Object.entries(citation.stage_scores ?? {});

  return (
    <article
      style={{ ["--d" as string]: `${Math.min(rank - 1, 5) * 110}ms` }}
      className="reveal group rounded-lg bg-card p-6 transition hover:bg-line/60 lg:p-8">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="font-mono text-xs text-muted">{String(rank).padStart(2, "0")}</span>
        <span className="inline-flex items-center gap-2 rounded-full bg-paper px-3 py-1 text-xs font-medium">
          <span className={"h-1.5 w-1.5 rounded-full " + status.dot} />
          {status.label}
        </span>
        <span className="font-mono text-xs text-muted">
          score {citation.score.toFixed(3)}
          {citation.published ? ` · ${citation.published}` : ""}
        </span>
      </div>

      <h3 className="mt-5 text-[22px] font-medium leading-tight tracking-tight">
        {prettyDoc(citation.doc_id)}
        {citation.section && <span className="text-muted"> · section {citation.section}</span>}
      </h3>
      <p className="mt-3 whitespace-pre-line text-[16px] leading-relaxed text-muted">{tidy(citation.snippet)}</p>

      {stages.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2 font-mono text-[11px] text-muted">
          {stages.map(([stage, score]) => (
            <span key={stage} className="rounded border border-line px-2 py-0.5">
              {stage} {score.toFixed(3)}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
