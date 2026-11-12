import { FormEvent, useState } from "react";
import { ArrowDot } from "./Icons";

interface SearchBarProps {
  onSearch: (question: string) => void;
  loading: boolean;
}

const EXAMPLE_QUERIES = [
  "Can I claim ITC on hotel stay?",
  "What was the rate on hotel accommodation in FY 2019-20?",
  "What is the late fee for not filing a return on time?",
  "When can the proper officer cancel a GST registration?",
];

export default function SearchBar({ onSearch, loading }: SearchBarProps) {
  const [question, setQuestion] = useState("");
  const ready = question.trim().length >= 3;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (ready) onSearch(question.trim());
  }

  return (
    <div>
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-3 rounded-xl bg-card p-2 sm:flex-row sm:items-center"
      >
        <label htmlFor="q" className="sr-only">
          Your GST question
        </label>
        <input
          id="q"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about ITC, returns, registration, rates…"
          className="min-w-0 flex-1 bg-transparent px-4 py-4 text-[clamp(18px,2vw,22px)] tracking-tight
                     placeholder:text-muted/70 focus:outline-none"
        />
        <button type="submit" disabled={loading || !ready} className="btn-dark justify-center py-4">
          {loading ? "Searching…" : "Search"}
          {!loading && <ArrowDot invert />}
        </button>
      </form>

      <div className="mt-4 flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setQuestion(example);
              onSearch(example);
            }}
            className="rounded-full border border-line px-4 py-2 text-sm text-muted transition
                       hover:border-ink hover:text-ink"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
