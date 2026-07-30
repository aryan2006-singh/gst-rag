import { FormEvent, useState } from "react";

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

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length >= 3) {
      onSearch(question.trim());
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Can I claim ITC on hotel stay?"
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-2.5
                     text-sm text-slate-900 placeholder:text-slate-400
                     focus:border-slate-500 focus:outline-none
                     dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="submit"
          disabled={loading || question.trim().length < 3}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white
                     disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setQuestion(example);
              onSearch(example);
            }}
            className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600
                       hover:border-slate-400 dark:border-slate-700 dark:text-slate-400"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
