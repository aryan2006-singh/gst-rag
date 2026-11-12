import type { Citation } from "../types";
import CitationCard from "./CitationCard";

export default function ResultsList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <div className="rounded-lg bg-card p-8 text-muted">
        No passages matched. Try different wording, or clear the “as of” date.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {citations.map((citation, i) => (
        <CitationCard key={citation.chunk_id} citation={citation} rank={i + 1} />
      ))}
    </div>
  );
}
