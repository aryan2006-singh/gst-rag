import type { Citation } from "../types";
import CitationCard from "./CitationCard";

export default function ResultsList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
        No passages retrieved.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {citations.map((citation) => (
        <CitationCard key={citation.chunk_id} citation={citation} />
      ))}
    </div>
  );
}
